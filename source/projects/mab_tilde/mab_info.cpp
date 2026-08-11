// mab.info -- Prozessisolierter Modell-Inspektor (analog nn.info)
//
// Kein PyTorch im Max-Prozess: mab.info startet inference_worker.py im
// --query-Modus, liest dessen stdout (JSON + MAB_INFO-Block) und stellt die
// Metadaten über 5 Message-Outlets bereit. Die Modell-Query läuft auf einem
// Hintergrund-Thread; Ergebnisse werden über ein t_qelem auf den Max-Haupt-
// Thread geliefert (kein UI-Freeze während des Modell-Loads).

// WIN32_LEAN_AND_MEAN, NOMINMAX and _CRT_SECURE_NO_WARNINGS are defined via
// CMake target_compile_definitions.

#include <windows.h>
#include <thread>
#include <string>
#include <cstring>
#include <cstdio>

#include "ext.h"
#include "ext_obex.h"
#include "ext_dictionary.h"
#include "ext_dictobj.h"
#include "max_path_resolve.h"
#include "worker_launch.h"

#define MAB_INFO_DICT_JSON 16384

static t_class* mab_info_class = nullptr;

typedef struct _mab_info {
    t_object ob;

    // Outlets (1..5 von links nach rechts)
    void* out_path;       // 1: model path (symbol)
    void* out_methods;    // 2: available methods (symbol)
    void* out_attributes; // 3: available attributes (symbol)
    void* out_params;     // 4: processing parameters (symbol + ints)
    void* out_dict;       // 5: dict output (dictionary)

    char model_path[MAX_PATH];

    // Query-Ergebnis-Cache (im Hintergrund-Thread gefüllt, auf dem
    // Haupt-Thread via qelem ausgegeben)
    long has_info;
    WorkerModelInfo info;
    char dict_json[MAB_INFO_DICT_JSON];

    // Threading
    std::thread* query_thread;
    t_qelem* result_qelem;
    long query_pending;

    // P11: download/delete/print_available_models (nn_tilde-Parität).
    // Der Worker läuft standalone (--download/--delete/--list) auf einem
    // eigenen Hintergrund-Thread; stdout wird auf Outlet 1 ausgegeben.
    std::thread* cmd_thread;
    t_qelem* cmd_qelem;         // Main-Thread-Trampolin für mab_info_apply_cmd
    long cmd_pending;           // 1 = Kommando läuft
    char cmd_args[1024];        // Argument-Zeile für worker_launch
    char cmd_result[8192];      // Worker-stdout (Ergebniszeilen)
    char cmd_error[512];        // Launch-/Netzwerk-Fehler
} t_mab_info;

// ============================================================================
// Query-Auswertung (thread-safe: schreibt nur in x, kein Max-SDK-Aufruf)
// ============================================================================

// Liest die komplette stdout-Pipe des Workers bis zum Prozess-Ende (polling,
// mit 90s Timeout). Schließt stdout_read. Da die Ausgaben klein sind, ist ein
// blockierender Pipe-Read hier unkritisch (Hintergrund-Thread).
static void mab_info_drain_stdout(const WorkerProcess* wp, std::string* text) {
    if (!wp || !wp->stdout_read) return;
    char buf[4096];
    DWORD available = 0;
    DWORD nread = 0;
    DWORD waited = 0;
    const DWORD timeout_ms = 90000;
    while (waited < timeout_ms) {
        if (!PeekNamedPipe(wp->stdout_read, NULL, 0, NULL, &available, NULL)) {
            break; // Pipe geschlossen -> EOF
        }
        if (available > 0) {
            if (ReadFile(wp->stdout_read, buf, sizeof(buf), &nread, NULL) &&
                nread > 0) {
                text->append(buf, nread);
                waited = 0;
                continue;
            }
        }
        if (WaitForSingleObject(wp->process, 100) == WAIT_OBJECT_0) {
            while (ReadFile(wp->stdout_read, buf, sizeof(buf), &nread, NULL) &&
                   nread > 0) {
                text->append(buf, nread);
            }
            break;
        }
        waited += 100;
    }
    CloseHandle(wp->stdout_read);
}

static void mab_info_query_thread(t_mab_info* x) {
    char argbuf[MAX_PATH * 2 + 32];
    snprintf(argbuf, sizeof(argbuf), "--query \"%s\"", x->model_path);

    WorkerProcess wp;
    worker_launch(argbuf, true, &wp);

    if (!wp.process) {
        snprintf(x->info.last_error, sizeof(x->info.last_error),
                 "Failed to launch Python worker.");
        x->has_info = 0;
        qelem_set(x->result_qelem);
        return;
    }

    std::string text;
    mab_info_drain_stdout(&wp, &text);
    WaitForSingleObject(wp.process, 1000);
    CloseHandle(wp.process);

    x->has_info = worker_parse_info_block(text.c_str(), &x->info) ? 1 : 0;
    if (!x->has_info && !x->info.last_error[0]) {
        snprintf(x->info.last_error, sizeof(x->info.last_error),
                 "Worker returned no MAB_INFO block.");
    }
    qelem_set(x->result_qelem);
}

// ============================================================================
// Dictionary-Ausgabe (Outlet 5)
// ============================================================================

static void mab_info_make_dict(t_mab_info* x, t_dictionary** out_dict) {
    t_dictionary* d = dictionary_new();
    if (x->has_info) {
        dictionary_appendstring(d, gensym("model_path"), x->model_path);
        dictionary_appendstring(d, gensym("model_type"), x->info.model_type);
        dictionary_appendlong(d, gensym("block_size"), x->info.block_size);
        dictionary_appendlong(d, gensym("channels_in"), x->info.channels_in);
        dictionary_appendlong(d, gensym("channels_out"), x->info.channels_out);
        dictionary_appendlong(d, gensym("latent_size"), x->info.latent_size);
        dictionary_appendstring(d, gensym("methods"), x->info.methods);
        dictionary_appendstring(d, gensym("attributes"), x->info.attributes);
        for (long i = 0; i < x->info.param_count; i++) {
            t_atom a[4];
            for (int j = 0; j < 4; j++)
                atom_setlong(&a[j], x->info.param_values[i][j]);
            dictionary_appendatoms(d, gensym(x->info.param_methods[i]), 4, a);
        }
    } else {
        dictionary_appendstring(d, gensym("error"), x->info.last_error);
    }
    *out_dict = d;
}

static void mab_info_out_dict(t_mab_info* x, t_dictionary* d) {
    t_atom a;
    atom_setobj(&a, d);
    dictobj_outlet_atoms(x->out_dict, 1, &a);
}

// ============================================================================
// Haupt-Thread: Query-Ergebnis ausgeben
// ============================================================================

static void mab_info_apply(t_mab_info* x) {
    x->query_pending = 0;
    if (!x->has_info) {
        post("mab.info: %s", x->info.last_error[0] ? x->info.last_error
                                                   : "No model information available.");
        return;
    }

    outlet_anything(x->out_path, gensym(x->model_path), 0, NULL);
    outlet_anything(x->out_methods, gensym(x->info.methods), 0, NULL);
    outlet_anything(x->out_attributes, gensym(x->info.attributes), 0, NULL);

    for (long i = 0; i < x->info.param_count; i++) {
        t_atom a[4];
        for (int j = 0; j < 4; j++)
            atom_setlong(&a[j], x->info.param_values[i][j]);
        outlet_anything(x->out_params, gensym(x->info.param_methods[i]), 4, a);
    }

    t_dictionary* d = nullptr;
    mab_info_make_dict(x, &d);
    if (d) mab_info_out_dict(x, d);
}

// ============================================================================
// P11: download/delete/print_available_models (standalone Worker-Läufe)
// ============================================================================

// Hintergrund-Thread: startet den Worker mit der in x->cmd_args stehenden
// Argument-Zeile, liest dessen stdout und liefert das Ergebnis über das
// cmd_qelem auf den Max-Haupt-Thread. Schreibt nur in x (kein Max-SDK-Call),
// analog zum Query-Thread.
static void mab_info_cmd_thread(t_mab_info* x) {
    WorkerProcess wp;
    worker_launch(x->cmd_args, true, &wp);

    if (!wp.process) {
        snprintf(x->cmd_error, sizeof(x->cmd_error),
                 "Failed to launch Python worker.");
        x->cmd_result[0] = '\0';
        qelem_set(x->cmd_qelem);
        return;
    }

    std::string text;
    mab_info_drain_stdout(&wp, &text);
    WaitForSingleObject(wp.process, 1000);
    CloseHandle(wp.process);

    if (!text.empty()) {
        // Nur die letzten 8KB behalten (--list kann mehrere Zeilen liefern).
        size_t n = text.size();
        const size_t maxlen = sizeof(x->cmd_result) - 1;
        if (n > maxlen) text = text.substr(n - maxlen);
        strncpy(x->cmd_result, text.c_str(), maxlen);
        x->cmd_result[maxlen] = '\0';
        x->cmd_error[0] = '\0';
    } else {
        snprintf(x->cmd_error, sizeof(x->cmd_error),
                 "Worker returned no output.");
        x->cmd_result[0] = '\0';
    }
    qelem_set(x->cmd_qelem);
}

// Haupt-Thread: Kommando-Ergebnis ausgeben. Fehler (Launch-/Netzwerkprobleme)
// werden als object_error gemeldet statt zu crashen; Ergebniszeilen gehen auf
// Outlet 1 (path).
static void mab_info_apply_cmd(t_mab_info* x) {
    x->cmd_pending = 0;
    if (x->cmd_error[0]) {
        object_error((t_object*)x, "mab.info: %s", x->cmd_error);
        return;
    }
    const char* p = x->cmd_result;
    while (p && *p) {
        const char* nl = strchr(p, '\n');
        size_t len = nl ? (size_t)(nl - p) : strlen(p);
        std::string line(p, len);
        while (!line.empty() && (line.back() == '\r' || line.back() == ' '))
            line.pop_back();
        if (!line.empty())
            outlet_anything(x->out_path, gensym(line.c_str()), 0, NULL);
        if (!nl) break;
        p = nl + 1;
    }
}

// Startet einen standalone-Worker-Lauf (nur ein Kommando gleichzeitig).
static void mab_info_run_command(t_mab_info* x, const char* arg_string) {
    if (x->cmd_pending) {
        post("mab.info: Command already running");
        return;
    }
    if (x->cmd_thread) {
        if (x->cmd_thread->joinable()) x->cmd_thread->join();
        delete x->cmd_thread;
        x->cmd_thread = nullptr;
    }
    strncpy(x->cmd_args, arg_string, sizeof(x->cmd_args) - 1);
    x->cmd_args[sizeof(x->cmd_args) - 1] = '\0';
    x->cmd_result[0] = '\0';
    x->cmd_error[0] = '\0';
    x->cmd_pending = 1;
    x->cmd_thread = new std::thread(mab_info_cmd_thread, x);
}

// ============================================================================
// Messages
// ============================================================================

static void mab_info_start_query(t_mab_info* x) {
    if (x->query_pending) {
        post("mab.info: Query already running for %s", x->model_path);
        return;
    }
    if (x->query_thread) {
        if (x->query_thread->joinable()) x->query_thread->join();
        delete x->query_thread;
        x->query_thread = nullptr;
    }
    x->query_pending = 1;
    x->query_thread = new std::thread(mab_info_query_thread, x);
}

static void mab_info_set(t_mab_info* x, t_symbol* s, long argc, t_atom* argv) {
    if (argc >= 1 && argv[0].a_type == A_SYM && argv[0].a_w.w_sym->s_name) {
        strncpy(x->model_path, argv[0].a_w.w_sym->s_name, sizeof(x->model_path) - 1);
        char resolved[MAX_PATH];
        if (mab_resolve_model_path(x->model_path, resolved, sizeof(resolved)))
            strncpy(x->model_path, resolved, sizeof(x->model_path) - 1);
        post("mab.info: Inspecting model %s", x->model_path);
        mab_info_start_query(x);
    } else {
        error("mab.info: set requires a model path argument");
    }
}

static void mab_info_path(t_mab_info* x, t_symbol* s, long argc, t_atom* argv) {
    if (argc >= 1 && argv[0].a_type == A_SYM && argv[0].a_w.w_sym->s_name) {
        mab_info_set(x, s, argc, argv);
    } else {
        outlet_anything(x->out_path, gensym(x->model_path), 0, NULL);
    }
}

static void mab_info_bang(t_mab_info* x) {
    if (x->has_info) {
        mab_info_apply(x);
    } else if (x->model_path[0]) {
        mab_info_start_query(x);
    } else {
        post("mab.info: No model loaded. Use [set <model>] or [path <model>].");
    }
}

static void mab_info_dump(t_mab_info* x) {
    if (!x->has_info) {
        if (x->info.last_error[0])
            post("mab.info: Error: %s", x->info.last_error);
        else
            post("mab.info: No model information available.");
        return;
    }
    post("mab.info: Model path      : %s", x->model_path);
    post("mab.info: Model type      : %s", x->info.model_type);
    post("mab.info: Block size      : %ld", x->info.block_size);
    post("mab.info: Channels in/out : %ld / %ld", x->info.channels_in,
         x->info.channels_out);
    post("mab.info: Latent size     : %ld", x->info.latent_size);
    post("mab.info: Methods         : %s", x->info.methods);
    post("mab.info: Attributes      : %s", x->info.attributes);
    for (long i = 0; i < x->info.param_count; i++) {
        post("mab.info:   %-8s in=%ld ratio=%ld out=%ld ratio=%ld",
             x->info.param_methods[i],
             x->info.param_values[i][0], x->info.param_values[i][1],
             x->info.param_values[i][2], x->info.param_values[i][3]);
    }
    mab_info_apply(x);
}

static void mab_info_methods(t_mab_info* x) {
    outlet_anything(x->out_methods, gensym(x->has_info ? x->info.methods : ""), 0, NULL);
}

static void mab_info_attributes(t_mab_info* x) {
    outlet_anything(x->out_attributes,
                    gensym(x->has_info ? x->info.attributes : ""), 0, NULL);
}

static void mab_info_parameters(t_mab_info* x, t_symbol* s, long argc, t_atom* argv) {
    if (!x->has_info) return;
    const char* want = (argc >= 1 && argv[0].a_type == A_SYM)
                           ? argv[0].a_w.w_sym->s_name : nullptr;
    for (long i = 0; i < x->info.param_count; i++) {
        if (want && strcmp(x->info.param_methods[i], want) != 0) continue;
        t_atom a[4];
        for (int j = 0; j < 4; j++)
            atom_setlong(&a[j], x->info.param_values[i][j]);
        outlet_anything(x->out_params, gensym(x->info.param_methods[i]), 4, a);
    }
}

static void mab_info_dump_dict(t_mab_info* x) {
    t_dictionary* d = nullptr;
    mab_info_make_dict(x, &d);
    if (d) mab_info_out_dict(x, d);
}

static void mab_info_dict(t_mab_info* x, t_symbol* name) {
    if (!name || !name->s_name) return;
    t_dictionary* d = nullptr;
    mab_info_make_dict(x, &d);
    if (!d) return;
    dictobj_register(d, &name);
    mab_info_out_dict(x, d);
}

// P11: download <card> [name] -> Worker --download (IRCAM Forum API).
static void mab_info_download(t_mab_info* x, t_symbol* s, long argc, t_atom* argv) {
    if (argc < 1 || argv[0].a_type != A_SYM || !argv[0].a_w.w_sym->s_name) {
        error("mab.info: download requires a model card "
              "(see print_available_models)");
        return;
    }
    const char* card = argv[0].a_w.w_sym->s_name;
    const char* name = (argc >= 2 && argv[1].a_type == A_SYM)
                           ? argv[1].a_w.w_sym->s_name : nullptr;
    char argbuf[1024];
    if (name && name[0])
        snprintf(argbuf, sizeof(argbuf), "--download \"%s\" \"%s\"", card, name);
    else
        snprintf(argbuf, sizeof(argbuf), "--download \"%s\"", card);
    mab_info_run_command(x, argbuf);
}

// P11: delete <model> -> Worker --delete.
static void mab_info_delete(t_mab_info* x, t_symbol* s, long argc, t_atom* argv) {
    if (argc < 1 || argv[0].a_type != A_SYM || !argv[0].a_w.w_sym->s_name) {
        error("mab.info: delete requires a model name "
              "(see print_available_models)");
        return;
    }
    char argbuf[1024];
    snprintf(argbuf, sizeof(argbuf), "--delete \"%s\"",
             argv[0].a_w.w_sym->s_name);
    mab_info_run_command(x, argbuf);
}

// P11: print_available_models -> Worker --list (lokale + Remote-Modelle).
static void mab_info_print(t_mab_info* x) {
    mab_info_run_command(x, "--list");
}

// ============================================================================
// Objekt-Lifecycle
// ============================================================================

static void* mab_info_new(t_symbol* s, long argc, t_atom* argv) {
    t_mab_info* x = (t_mab_info*)object_alloc(mab_info_class);
    if (!x) return nullptr;

    x->out_dict = outlet_new(x, NULL);
    x->out_params = outlet_new(x, NULL);
    x->out_attributes = outlet_new(x, NULL);
    x->out_methods = outlet_new(x, NULL);
    x->out_path = outlet_new(x, NULL);

    x->model_path[0] = '\0';
    x->has_info = 0;
    x->query_thread = nullptr;
    x->query_pending = 0;
    x->result_qelem = qelem_new(x, (method)mab_info_apply);
    ZeroMemory(&x->info, sizeof(x->info));
    x->dict_json[0] = '\0';

    // P11: download/delete/print-Kommandos
    x->cmd_thread = nullptr;
    x->cmd_pending = 0;
    x->cmd_args[0] = '\0';
    x->cmd_result[0] = '\0';
    x->cmd_error[0] = '\0';
    x->cmd_qelem = qelem_new(x, (method)mab_info_apply_cmd);

    if (argc >= 1 && argv[0].a_type == A_SYM && argv[0].a_w.w_sym->s_name) {
        strncpy(x->model_path, argv[0].a_w.w_sym->s_name, sizeof(x->model_path) - 1);
        char resolved[MAX_PATH];
        if (mab_resolve_model_path(x->model_path, resolved, sizeof(resolved)))
            strncpy(x->model_path, resolved, sizeof(x->model_path) - 1);
        mab_info_start_query(x);
    }
    return x;
}

static void mab_info_free(t_mab_info* x) {
    if (x->query_thread) {
        if (x->query_thread->joinable()) x->query_thread->join();
        delete x->query_thread;
        x->query_thread = nullptr;
    }
    if (x->result_qelem) {
        qelem_unset(x->result_qelem);
        qelem_free(x->result_qelem);
        x->result_qelem = nullptr;
    }
    // P11: Kommando-Thread beenden bevor das qelem freigegeben wird.
    if (x->cmd_thread) {
        if (x->cmd_thread->joinable()) x->cmd_thread->join();
        delete x->cmd_thread;
        x->cmd_thread = nullptr;
    }
    if (x->cmd_qelem) {
        qelem_unset(x->cmd_qelem);
        qelem_free(x->cmd_qelem);
        x->cmd_qelem = nullptr;
    }
}

static void mab_info_assist(t_mab_info* x, void* b, long m, long a, char* s) {
    if (m == ASSIST_INLET) {
        sprintf(s, "(messages) Model inspection. Use [set <model>], [path <model>], [bang], "
                   "[download <card> [name]], [delete <model>], [print_available_models]");
    } else {
        switch (a) {
            case 0: sprintf(s, "(symbol) Model path"); break;
            case 1: sprintf(s, "(symbol) Available methods"); break;
            case 2: sprintf(s, "(symbol) Available attributes"); break;
            case 3: sprintf(s, "(list) Processing parameters"); break;
            default: sprintf(s, "(dictionary) Dict output"); break;
        }
    }
}

// ============================================================================
// Entry point
// ============================================================================

extern "C" __declspec(dllexport) void ext_main(void* r) {
    t_class* c = class_new("mab.info",
                           (method)mab_info_new,
                           (method)mab_info_free,
                           (long)sizeof(t_mab_info),
                           0L,
                           A_GIMME,
                           0);

    class_addmethod(c, (method)mab_info_bang, "bang", 0);
    class_addmethod(c, (method)mab_info_set, "set", A_GIMME, 0);
    class_addmethod(c, (method)mab_info_path, "path", A_GIMME, 0);
    class_addmethod(c, (method)mab_info_dump, "dump", 0);
    class_addmethod(c, (method)mab_info_methods, "methods", 0);
    class_addmethod(c, (method)mab_info_attributes, "attributes", 0);
    class_addmethod(c, (method)mab_info_parameters, "parameters", A_GIMME, 0);
    class_addmethod(c, (method)mab_info_dump_dict, "dump_dict", 0);
    class_addmethod(c, (method)mab_info_dict, "dict", A_SYM, 0);
    class_addmethod(c, (method)mab_info_download, "download", A_GIMME, 0);
    class_addmethod(c, (method)mab_info_delete, "delete", A_GIMME, 0);
    class_addmethod(c, (method)mab_info_print, "print_available_models", 0);
    class_addmethod(c, (method)mab_info_assist, "assist", A_CANT, 0);

    class_register(CLASS_BOX, c);
    mab_info_class = c;

    post("mab.info: Native Max SDK external loaded successfully.");
}
