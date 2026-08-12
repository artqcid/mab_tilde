// WIN32_LEAN_AND_MEAN and NOMINMAX are defined via CMake target_compile_definitions
#include <windows.h>
#include <thread>
#include <atomic>
#include <process.h>
#include <string>
#include <cstring>
#include <cstdio>

#include "ext.h"
#include "ext_obex.h"
#include "z_dsp.h"
#include "block_accumulator.h"
#include "max_path_resolve.h"
#include "worker_launch.h"
// P7 (Vorbereitung): Buffer~-Tracking. Muss NACH ext.h inkludiert werden
// (nutzt t_symbol aus dem Max-SDK).
#include "buffer_manager.h"

// Constants for shared memory sizing
#define MAX_CHANNELS 16
#define MAX_BLOCK_SIZE 4096
#define CONTROL_RING_SIZE 256
#define CONTROL_MSG_SIZE 256

// Control message ring buffer (lock-free SPSC)
struct ControlRingBuffer {
    long head;                           // Written by C++ (producer)
    long tail;                           // Written by Python (consumer)
    char messages[CONTROL_RING_SIZE][CONTROL_MSG_SIZE];
};

// Shared memory header structure (C-compatible, no C++ objects).
// Version 3 adds method-aware metadata (v2) plus the per-inlet MC channel map
// so C++ can rebuild inlets/outlets dynamically and Python knows how many
// channels are actually connected to each mc.mab~ inlet.
// Field order MUST match the Python SharedMemoryHeader exactly.
struct SharedMemoryHeader {
    uint32_t magic;           // 0x4D414254 ('MABT')
    uint32_t version;         // 3
    uint32_t block_size;      // samples per audio block (latent held at audio rate)
    uint32_t num_channels;    // legacy channel count (== channels_out)
    uint32_t channels_in;     // active method: input channels
    uint32_t channels_out;    // active method: output channels
    uint32_t latent_size;     // latent dimension of the active method
    uint32_t input_ratio;     // active method: input ratio
    uint32_t output_ratio;    // active method: output ratio
    char     method[52];      // active method name (forward/encode/decode/prior)
    uint32_t method_id;       // stable hash of method for atomic comparison
    uint32_t input_offset;    // bytes to input buffer 0
    uint32_t output_offset;   // bytes to output buffer 0
    uint32_t control_offset;  // bytes to control ring buffer
    uint32_t input_buffer_index;   // A1: index of input buffer C++ is filling (0/1)
    uint32_t output_buffer_index;  // A1: index of output buffer C++ is draining (0/1)
    uint32_t channel_map[16]; // Phase 5 (mc.mab~): per-inlet channel counts
    long is_input_ready;      // atomic flag (volatile)
    long is_output_ready;     // atomic flag (volatile)
    long is_python_ready;     // atomic flag (volatile)
    long shutdown_flag;       // atomic flag (C++ tells Python to die)
};

// Compile-time check that both sides agree on the header size.
// 9x uint32 (36) + method[52] + method_id (4) + 3x uint32 (12) +
// 2x uint32 (8) + 16x uint32 channel_map (64) + 4x long (16) = 192 bytes.
static_assert(sizeof(SharedMemoryHeader) == 192,
              "SharedMemoryHeader v3 must be 192 bytes (sync with Python)");

static t_class* mab_tilde_class = nullptr;
static t_class* mc_mab_tilde_class = nullptr;
static t_class* mcs_mab_tilde_class = nullptr;

typedef struct _mab_tilde {
    t_pxobject ob;
    long is_ready;           // 1 = Python is connected & ready
    long is_bypass;          // 1 = bypass audio processing
    
    // Threading & Process
    std::thread* init_thread;
    HANDLE python_process;
    HANDLE ready_event;
    HANDLE input_ready_event;
    HANDLE hMapFile;

    // Shared Memory pointers
    SharedMemoryHeader* header; // THIS is crucial for IPC!
    float* p_input;
    float* p_output;
    ControlRingBuffer* p_control;  // Control message ring buffer
    
    // Arguments
    char model_path[256];
    char method_name[64];
    long buffer_size;
    long gpu;
    long cores;            // PyTorch-Inferenz-Threads (Default 2, Clamp 1..64)
    
    // Runtime state
    long num_channels;
    
    // Phase 3: method-aware IO layout (cached copy of the header's active method)
    char active_method[64];
    uint32_t active_method_id; // stable hash of active_method for atomic compare
    long channels_in;          // inlet count of the active method
    long channels_out;         // outlet count of the active method
    long in_pos;               // input accumulation position within one block
    long out_pos;              // output drain position within one block
    long method_pending;       // 1 = IO rebuild queued (qelem) but not applied
    
    // Control message buffer for anything forwarding
    char control_buffer[1024];
    long control_size;

    // P7 (Vorbereitung): Buffer~-Tracking. Wird in Phase 5 mit dem nativen
    // Max-SDK buffer_reference verbunden (track_buffers/notify/set <attr>).
    BufferManager buffer_mgr;
    
    // Main-thread communication: qelem fires mab_tilde_apply_io on the Max
    // main thread (dsp_resize / outlet rebuild must never run on the audio
    // thread or the background init thread).
    t_qelem* io_qelem;

    // A2: periodic crash check timer (main thread, not audio thread)
    t_clock* crash_clock;

    // B5: GPU reload bypass timer (prevents race during async model reload)
    t_clock* gpu_reload_clock;

    // Phase 5: mc.mab~ (Multichannel) support fields
    long is_mc;                // 1 = mc.mab~ mode, 0 = mab~ mode
    long channel_map[16];      // per-inlet channel count (MC mode, max 16 inlets)
    long n_batches;            // fixed output channels from `chans` attribute (0 = auto)
    long last_io_in;           // B4: last rebuilt inlet count (avoid unnecessary rebuild)
    long last_io_out;          // B4: last rebuilt outlet count

    // Phase 6: mcs.mab~ (Batched Multichannel) support fields
    long is_mcs;               // 1 = mcs.mab~ mode, 0 = mab~/mc.mab~ mode
    long mcs_batches;          // number of batch inlets/outlets (mcs.mab~, 1..16)
} t_mab_tilde;

// Phase 6: shared prefix helper so all variants post the correct class name.
static const char* mab_tilde_prefix(t_mab_tilde* x) {
    if (x->is_mcs) return "mcs.mab~";
    if (x->is_mc) return "mc.mab~";
    return "mab~";
}

// ============================================================================
// ALL Max SDK methods must be declared in extern "C" block
// ============================================================================
extern "C" {
    // Forward declaration for the background thread function
    void init_worker(t_mab_tilde* x);
    void init_worker_thread(t_mab_tilde* x);

    // Core methods
    void* mab_tilde_new(t_symbol* s, long argc, t_atom* argv);
    void mab_tilde_free(t_mab_tilde* x);
    void mab_tilde_assist(t_mab_tilde* x, void* b, long m, long a, char* s);
    void mab_tilde_dsp64(t_mab_tilde* x, t_object* dsp64, short* count, double samplerate, long maxvectorsize, long flags);
    void mab_tilde_perform64(t_mab_tilde* x, t_object* dsp64, double** ins, long numins, double** outs, long numouts, long sampleframes, long flags, void* userparam);
    
    // Phase 1.7 Message Handlers
    void mab_tilde_enable(t_mab_tilde* x, long flag);
    void mab_tilde_gpu(t_mab_tilde* x, long flag);
    void mab_tilde_reload(t_mab_tilde* x, t_symbol* s);
    void mab_tilde_dump(t_mab_tilde* x);
    void mab_tilde_set(t_mab_tilde* x, t_symbol* s, long argc, t_atom* argv);
    void mab_tilde_get(t_mab_tilde* x, t_symbol* s);
    void mab_tilde_method(t_mab_tilde* x, t_symbol* s, long argc, t_atom* argv);
    void mab_tilde_load(t_mab_tilde* x, t_symbol* s);
    void mab_tilde_anything(t_mab_tilde* x, t_symbol* s, long argc, t_atom* argv);

    // Phase 3: main-thread IO rebuild (fired via t_qelem from the audio
    // thread or the background init thread - never call dsp_resize directly
    // from those threads).
    void mab_tilde_apply_io(t_mab_tilde* x);

    // A2: crash monitoring on main thread (not in perform64)
    void mab_tilde_check_crash(t_mab_tilde* x);

    // B5: GPU reload bypass clear timer callback
    void mab_tilde_gpu_reload_done(t_mab_tilde* x);

    // Phase 5: mc.mab~ (Multichannel)
    void* mc_mab_tilde_new(t_symbol* s, long argc, t_atom* argv);
    void mc_mab_tilde_dsp64(t_mab_tilde* x, t_object* dsp64, short* count, double samplerate, long maxvectorsize, long flags);
    void mc_mab_tilde_perform64(t_mab_tilde* x, t_object* dsp64, double** ins, long numins, double** outs, long numouts, long sampleframes, long flags, void* userparam);
    long mc_multichanneloutputs(t_mab_tilde* x, long index, long count);
    long mc_inputchanged(t_mab_tilde* x, long index, long count);
    void mc_mab_tilde_chans(t_mab_tilde* x, long n);

    // Phase 6: mcs.mab~ (Batched Multichannel)
    void* mcs_mab_tilde_new(t_symbol* s, long argc, t_atom* argv);
    void mcs_mab_tilde_dsp64(t_mab_tilde* x, t_object* dsp64, short* count, double samplerate, long maxvectorsize, long flags);
    void mcs_mab_tilde_perform64(t_mab_tilde* x, t_object* dsp64, double** ins, long numins, double** outs, long numouts, long sampleframes, long flags, void* userparam);
    long mcs_multichanneloutputs(t_mab_tilde* x, long index, long count);
    long mcs_inputchanged(t_mab_tilde* x, long index, long count);

    // Shared helper for MC and mono IO rebuild
    void mab_tilde_rebuild_io(t_mab_tilde* x, long new_in, long new_out);

    __declspec(dllexport) void ext_main(void* r);
}

// ============================================================================
// Phase 5/6 ext_main: compiled three times via CMake target_compile_definitions.
// mab~.mxe64:     no define            → registers mab~ class only.
// mc.mab~.mxe64:  MC_MAB_TILDE_MODULE  → registers mc.mab~ class only.
// mcs.mab~.mxe64: MCS_MAB_TILDE_MODULE → registers mcs.mab~ class only.
// ============================================================================
#if defined(MCS_MAB_TILDE_MODULE)
void ext_main(void* r) {
    t_class* mcs_class = class_new("mcs.mab~",
                                   (method)mcs_mab_tilde_new,
                                   (method)mab_tilde_free,
                                   (long)sizeof(t_mab_tilde),
                                   0L,
                                   A_GIMME,
                                   0);

    class_addmethod(mcs_class, (method)mcs_mab_tilde_dsp64, "dsp64", A_CANT, 0);
    class_addmethod(mcs_class, (method)mab_tilde_assist, "assist", A_CANT, 0);

    // MC-specific callbacks (nn_tilde-Parität P9: mcs = wie mc + n_batches)
    class_addmethod(mcs_class, (method)mcs_multichanneloutputs, "multichanneloutputs", A_CANT, 0);
    class_addmethod(mcs_class, (method)mcs_inputchanged, "inputchanged", A_CANT, 0);

    // chans attribute: fixed per-batch output channel count (nn_tilde-Parität P8/P9)
    class_addmethod(mcs_class, (method)mc_mab_tilde_chans, "chans", A_LONG, 0);

    // Shared message handlers (same as mab~ / mc.mab~)
    class_addmethod(mcs_class, (method)mab_tilde_enable, "enable", A_LONG, 0);
    class_addmethod(mcs_class, (method)mab_tilde_gpu, "gpu", A_LONG, 0);
    class_addmethod(mcs_class, (method)mab_tilde_reload, "reload", A_SYM, 0);
    class_addmethod(mcs_class, (method)mab_tilde_dump, "dump", 0);
    class_addmethod(mcs_class, (method)mab_tilde_set, "set", A_GIMME, 0);
    class_addmethod(mcs_class, (method)mab_tilde_get, "get", A_SYM, 0);
    class_addmethod(mcs_class, (method)mab_tilde_method, "method", A_GIMME, 0);
    class_addmethod(mcs_class, (method)mab_tilde_load, "load", A_SYM, 0);
    class_addmethod(mcs_class, (method)mab_tilde_anything, "anything", A_GIMME, 0);

    class_dspinit(mcs_class);
    class_register(CLASS_BOX, mcs_class);
    mcs_mab_tilde_class = mcs_class;

    post("mcs.mab~: Batched multichannel external loaded successfully.");
}
#elif defined(MC_MAB_TILDE_MODULE)
void ext_main(void* r) {
    t_class* mc_class = class_new("mc.mab~",
                                  (method)mc_mab_tilde_new,
                                  (method)mab_tilde_free,
                                  (long)sizeof(t_mab_tilde),
                                  0L,
                                  A_GIMME,
                                  0);

    class_addmethod(mc_class, (method)mc_mab_tilde_dsp64, "dsp64", A_CANT, 0);
    class_addmethod(mc_class, (method)mab_tilde_assist, "assist", A_CANT, 0);

    // MC-specific callbacks (nn_tilde-Parität P8)
    class_addmethod(mc_class, (method)mc_multichanneloutputs, "multichanneloutputs", A_CANT, 0);
    class_addmethod(mc_class, (method)mc_inputchanged, "inputchanged", A_CANT, 0);

    // Phase 5: chans attribute (fixed output channel count, nn_tilde-Parität P8)
    class_addmethod(mc_class, (method)mc_mab_tilde_chans, "chans", A_LONG, 0);

    // Shared message handlers (same as mab~)
    class_addmethod(mc_class, (method)mab_tilde_enable, "enable", A_LONG, 0);
    class_addmethod(mc_class, (method)mab_tilde_gpu, "gpu", A_LONG, 0);
    class_addmethod(mc_class, (method)mab_tilde_reload, "reload", A_SYM, 0);
    class_addmethod(mc_class, (method)mab_tilde_dump, "dump", 0);
    class_addmethod(mc_class, (method)mab_tilde_set, "set", A_GIMME, 0);
    class_addmethod(mc_class, (method)mab_tilde_get, "get", A_SYM, 0);
    class_addmethod(mc_class, (method)mab_tilde_method, "method", A_GIMME, 0);
    class_addmethod(mc_class, (method)mab_tilde_load, "load", A_SYM, 0);
    class_addmethod(mc_class, (method)mab_tilde_anything, "anything", A_GIMME, 0);

    class_dspinit(mc_class);
    class_register(CLASS_BOX, mc_class);
    mc_mab_tilde_class = mc_class;

    post("mc.mab~: Multichannel external loaded successfully.");
}
#else
void ext_main(void* r) {
    t_class* c = class_new("mab~",
                           (method)mab_tilde_new,
                           (method)mab_tilde_free,
                           (long)sizeof(t_mab_tilde),
                           0L,
                           A_GIMME,
                           0);

    class_addmethod(c, (method)mab_tilde_dsp64, "dsp64", A_CANT, 0);
    class_addmethod(c, (method)mab_tilde_assist, "assist", A_CANT, 0);
    
    // Message handlers (Phase 1.7)
    class_addmethod(c, (method)mab_tilde_enable, "enable", A_LONG, 0);
    class_addmethod(c, (method)mab_tilde_gpu, "gpu", A_LONG, 0);
    class_addmethod(c, (method)mab_tilde_reload, "reload", A_SYM, 0);
    class_addmethod(c, (method)mab_tilde_dump, "dump", 0);
    class_addmethod(c, (method)mab_tilde_set, "set", A_GIMME, 0);
    class_addmethod(c, (method)mab_tilde_get, "get", A_SYM, 0);
    class_addmethod(c, (method)mab_tilde_method, "method", A_GIMME, 0);
    class_addmethod(c, (method)mab_tilde_load, "load", A_SYM, 0);
    class_addmethod(c, (method)mab_tilde_anything, "anything", A_GIMME, 0);

    class_dspinit(c);
    class_register(CLASS_BOX, c);
    mab_tilde_class = c;

    post("mab~: Native Max SDK external loaded successfully.");
}
#endif

void* mab_tilde_new(t_symbol* s, long argc, t_atom* argv) {
    t_mab_tilde* x = (t_mab_tilde*)object_alloc(mab_tilde_class);
    if (!x) return nullptr;

    dsp_setup((t_pxobject*)x, 1);
    outlet_new(x, "signal");

    // Initialize variables (Clean state - No Model loaded initially)
    x->is_ready = 0;
    x->is_bypass = 1; 
    x->num_channels = 1; 
    
    x->init_thread = nullptr;
    x->python_process = nullptr;
    x->ready_event = nullptr;
    x->input_ready_event = nullptr;
    x->hMapFile = nullptr;
    x->header = nullptr;
    x->p_input = nullptr;
    x->p_output = nullptr;
    x->p_control = nullptr;

    x->model_path[0] = '\0';
    x->method_name[0] = '\0';
    x->buffer_size = 512;
    x->gpu = 0;
    x->cores = 2;   // Default: 2 PyTorch-Inferenz-Threads (Clamping 1..64)
    x->control_size = 0;
    memset(x->control_buffer, 0, sizeof(x->control_buffer));

    // P7 (Vorbereitung): Buffer~-Tracking initialisieren
    buffer_manager_init(&x->buffer_mgr);

    // Phase 3: method-aware IO state (default 1-in/1-out until the worker
    // reports the real layout through the shared-memory header)
    x->active_method[0] = '\0';
    x->active_method_id = 0;
    x->channels_in = 1;
    x->channels_out = 1;
    x->in_pos = 0;
    x->out_pos = 0;
    x->method_pending = 0;
    x->io_qelem = qelem_new(x, (method)mab_tilde_apply_io);
     x->crash_clock = clock_new(x, (method)mab_tilde_check_crash);
    x->gpu_reload_clock = clock_new(x, (method)mab_tilde_gpu_reload_done);

    // Phase 5: MC fields (mab~ mode: is_mc=0)
    x->is_mc = 0;
    x->n_batches = 0;
    for (long i = 0; i < 16; i++) x->channel_map[i] = 0;
    x->last_io_in = 1;   // dsp_setup(x,1) + outlet_new in constructor
    x->last_io_out = 1;

    // Parse arguments safely (Optional, exactly like nn_tilde)

    // Void-Modus (nn_tilde-Parität P5): `mab~ void <inlets> <outlets> <bufsize>`
    // erzeugt einen reinen Passthrough mit N Inlets/Outlets und startet KEINEN
    // Worker (kein Modell). Puffer-Zeichenketten usw. werden ignoriert.
    long void_mode = 0;
    if (argc >= 1) {
        t_symbol* first = atom_getsym(argv);
        if (first && first->s_name && strcmp(first->s_name, "void") == 0)
            void_mode = 1;
    }

    if (argc >= 1 && !void_mode) {
        t_symbol* model_sym = atom_getsym(argv);
        if (model_sym && model_sym->s_name) {
            strncpy(x->model_path, model_sym->s_name, sizeof(x->model_path) - 1);
            char resolved[MAX_PATH];
            if (mab_resolve_model_path(x->model_path, resolved, sizeof(resolved)))
                strncpy(x->model_path, resolved, sizeof(x->model_path) - 1);
        }
    }
    // B3 fix: auto-detect if user skipped the optional method argument.
    // If argv[1] is a number, the user wrote e.g. [mab~ model bufsize gpu]
    // instead of [mab~ model method bufsize gpu]. Shift numeric args by -1.
    bool has_method = false;
    if (argc >= 2 && !void_mode) {
        if (argv[1].a_type != A_LONG && argv[1].a_type != A_FLOAT) {
            has_method = true;
        }
    }

    if (has_method) {
        t_symbol* method_sym = atom_getsym(argv + 1);
        if (method_sym && method_sym->s_name) {
            strncpy(x->method_name, method_sym->s_name, sizeof(x->method_name) - 1);
        }
    }

    long off = has_method ? 2 : 1;
    if (argc > off && !void_mode)     x->buffer_size = atom_getlong(argv + off);
    if (argc > off+1 && !void_mode)   x->gpu = atom_getlong(argv + off+1);
    if (argc > off+2 && !void_mode)   x->num_channels = atom_getlong(argv + off+2);
    if (argc > off+3 && !void_mode) {
        x->cores = atom_getlong(argv + off+3);
        if (x->cores < 1) x->cores = 1;
        if (x->cores > 64) x->cores = 64;
    }

    if (void_mode) {
        // mab~ void <inlets> <outlets> <bufsize>
        long n_in = (argc >= 2) ? atom_getlong(argv + 1) : 1;
        long n_out = (argc >= 3) ? atom_getlong(argv + 2) : 1;
        if (argc >= 4) x->buffer_size = atom_getlong(argv + 3);
        if (n_in < 1) n_in = 1;
        if (n_out < 1) n_out = 1;
        if (n_in > MAX_CHANNELS) n_in = MAX_CHANNELS;
        if (n_out > MAX_CHANNELS) n_out = MAX_CHANNELS;
        x->channels_in = n_in;
        x->channels_out = n_out;
        x->num_channels = n_out;
        strncpy(x->active_method, "forward", sizeof(x->active_method) - 1);
        x->active_method[sizeof(x->active_method) - 1] = '\0';
        x->active_method_id = 0;   // hash("forward") placeholder; void mode uses layout only

        // Inlets/Outlets direkt auf dem Main-Thread einrichten (wir sind in
        // mab_tilde_new, kein Thread-Kontext-Wechsel nötig).
        dsp_resize((t_pxobject*)x, n_in);
        while (x->ob.z_ob.o_outlet) {
            object_free((t_object*)x->ob.z_ob.o_outlet);
        }
        for (long i = 0; i < n_out; i++) {
            outlet_new((t_object*)x, "signal");
        }
        post("mab~: void mode: %ld inlets, %ld outlets, buffer_size=%ld",
             n_in, n_out, x->buffer_size);
        return x;
    }

    // If a model path was provided at creation time, start the worker immediately.
    // Otherwise, start in "No Model" idle state waiting for a [load] message.
    if (x->model_path[0] != '\0') {
        x->init_thread = new std::thread(init_worker_thread, x);
    } else {
        post("mab~: Created in 'no model' state. Use [load <model>] to start.");
    }
    
    return x;
}

void mab_tilde_free(t_mab_tilde* x) {
    // 1. Tell Python to shutdown via shared memory
    if (x->header) {
        InterlockedExchange(&x->header->shutdown_flag, 1);
    }
    if (x->ready_event) {
        SetEvent(x->ready_event);
    }

    // 2. Wait for the background thread to finish cleanly
    if (x->init_thread) {
        if (x->init_thread->joinable()) {
            x->init_thread->join();
        }
        delete x->init_thread;
        x->init_thread = nullptr;
    }

    // 3. Cleanup Python Process
    if (x->python_process) {
        DWORD waitResult = WaitForSingleObject(x->python_process, 500);
        if (waitResult == WAIT_TIMEOUT) {
            TerminateProcess(x->python_process, 1);
        }
        CloseHandle(x->python_process);
    }

    // 4. Cleanup Shared Memory
    if (x->header) {
        UnmapViewOfFile(x->header);
    }
    if (x->hMapFile) {
        CloseHandle(x->hMapFile);
    }
    if (x->ready_event) {
        CloseHandle(x->ready_event);
    }
    if (x->input_ready_event) {
        CloseHandle(x->input_ready_event);
    }

    // 5. Cleanup main-thread IO communication (must happen after the init
    //    thread has been joined so no pending qelem fires on a freed object)
    if (x->io_qelem) {
        qelem_unset(x->io_qelem);
        qelem_free(x->io_qelem);
        x->io_qelem = nullptr;
    }
    if (x->crash_clock) {
        clock_unset(x->crash_clock);
        clock_free(x->crash_clock);
        x->crash_clock = nullptr;
    }
    if (x->gpu_reload_clock) {
        clock_unset(x->gpu_reload_clock);
        clock_free(x->gpu_reload_clock);
        x->gpu_reload_clock = nullptr;
    }

    dsp_free((t_pxobject*)x);
}

void mab_tilde_assist(t_mab_tilde* x, void* b, long m, long a, char* s) {
    // Phase 3: methoden-abhängige Labels (nn_tilde-Parität). decode/prior:
    // Latent-Inlets + Audio-Outlets; encode: Audio-Inlet + Latent-Outlets.
    const char* method = x->active_method[0] ? x->active_method : x->method_name;
    bool is_latent_in = (strcmp(method, "decode") == 0 ||
                         strcmp(method, "prior") == 0);
    bool is_latent_out = (strcmp(method, "encode") == 0);
    if (m == ASSIST_INLET) {
        if (is_latent_in)
            sprintf(s, "(signal) latent input %ld", a + 1);
        else if (method[0])
            sprintf(s, "(signal) audio input %ld", a + 1);
        else
            sprintf(s, "(signal) Audio Input %ld", a + 1);
    } else {
        if (is_latent_out)
            sprintf(s, "(signal) latent output %ld", a + 1);
        else if (method[0])
            sprintf(s, "(signal) audio output %ld", a + 1);
        else
            sprintf(s, "(signal) Audio Output %ld", a + 1);
    }
}

void mab_tilde_dsp64(t_mab_tilde* x, t_object* dsp64, short* count, double samplerate, long maxvectorsize, long flags) {
    object_method(dsp64, gensym("dsp_add64"), x, mab_tilde_perform64, 0, NULL);
}

// A2: crash monitoring runs on the Max main thread (clock callback), not in
// perform64. This removes the last Win32 syscall from the audio callback.
void mab_tilde_check_crash(t_mab_tilde* x) {
    if (!x->is_ready || !x->python_process) {
        return;
    }

    DWORD exitCode = 0;
    if (!GetExitCodeProcess(x->python_process, &exitCode)) {
        // Failed to query; try again later
        clock_fdelay(x->crash_clock, 100.0);
        return;
    }

    if (exitCode != STILL_ACTIVE) {
        post("mab~: Python worker crashed. Check mab_worker.log for details (e.g. VRAM).");
        InterlockedExchange(&x->is_ready, 0);
        InterlockedExchange(&x->is_bypass, 1);
        x->in_pos = 0;
        x->out_pos = 0;
        if (x->header) {
            UnmapViewOfFile(x->header);
            x->header = nullptr;
            x->p_input = nullptr;
            x->p_output = nullptr;
            x->p_control = nullptr;
        }
        if (x->hMapFile) {
            CloseHandle(x->hMapFile);
            x->hMapFile = nullptr;
        }
        if (x->input_ready_event) {
            CloseHandle(x->input_ready_event);
            x->input_ready_event = nullptr;
        }
        if (x->python_process) {
            CloseHandle(x->python_process);
            x->python_process = nullptr;
        }
        // Stop rescheduling; object is now in bypass.
        return;
    }

    // Still alive: reschedule next check in 100 ms.
    clock_fdelay(x->crash_clock, 100.0);
}

void mab_tilde_perform64(t_mab_tilde* x, t_object* dsp64, double** ins, long numins, double** outs, long numouts, long sampleframes, long flags, void* userparam) {
    long n = sampleframes;
    if (n < 0) n = 0;

    // Bypass mode: pass audio through unchanged when not ready (channel-wise
    // so multi-channel layouts like decode don't collapse to a single channel).
    if (!x->is_ready || x->is_bypass || !x->header) {
        long pass = (numins < numouts) ? numins : numouts;
        for (long ch = 0; ch < numouts; ch++) {
            double* out = outs[ch];
            double* in = (ch < pass && ins[ch]) ? ins[ch] : nullptr;
            for (long i = 0; i < n; i++) out[i] = in ? in[i] : 0.0;
        }
        return;
    }

    const long blk = (long)x->header->block_size;
    if (blk < 1) {
        for (long ch = 0; ch < numouts; ch++)
            for (long i = 0; i < n; i++) outs[ch][i] = 0.0;
        return;
    }
    const long channels_in = x->channels_in;
    const long channels_out = x->channels_out;

    // Phase 3: method-change detection. Python switches the method by writing
    // header->method; we must NOT call dsp_resize/outlet_new from the audio
    // thread, so we queue a qelem that fires mab_tilde_apply_io on the main
    // thread. Until then the old layout stays valid (it still matches the
    // currently wired inlets/outlets). A channel-count change (e.g. [load] of
    // a different model with the same method name) also triggers a rebuild.
    if (!x->method_pending &&
        (x->header->method_id != x->active_method_id ||
         (long)x->header->channels_in != x->channels_in ||
         (long)x->header->channels_out != x->channels_out)) {
        x->method_pending = 1;
        qelem_set(x->io_qelem);
    }

    const size_t input_buffer_stride = (size_t)channels_in * (size_t)blk;
    const size_t output_buffer_stride = (size_t)channels_out * (size_t)blk;

    // A1: Double-buffered input. C++ fills the buffer indexed by
    // header->input_buffer_index; when it is full we hand it over to Python
    // and immediately start filling the other buffer.
    if (x->header->is_input_ready == 0) {
        uint32_t in_idx = x->header->input_buffer_index & 1;
        float* input_ptr = x->p_input + in_idx * input_buffer_stride;
        if (block_accumulate_write(input_ptr, channels_in, blk, n,
                                   ins, numins, x->in_pos)) {
            // Switch to the other input buffer before signalling readiness so
            // the next audio tick can keep accumulating while Python infers.
            x->header->input_buffer_index = 1 - in_idx;
            InterlockedExchange(&x->header->is_input_ready, 1);
            // A4: wake Python immediately instead of letting it sleep-poll.
            if (x->input_ready_event) {
                SetEvent(x->input_ready_event);
            }
        }
    }

    // A1: Double-buffered output. C++ drains the buffer indexed by
    // header->output_buffer_index; when it is empty we switch to the other
    // buffer that Python has (or will) fill next.
    if (x->header->is_output_ready == 1) {
        uint32_t out_idx = x->header->output_buffer_index & 1;
        float* output_ptr = x->p_output + out_idx * output_buffer_stride;
        if (block_accumulate_read(output_ptr, channels_out, blk, n,
                                  outs, numouts, x->out_pos)) {
            InterlockedExchange(&x->header->is_output_ready, 0);
            x->header->output_buffer_index = 1 - out_idx;
        }
    } else {
        // Python has not produced the next block yet: output silence so no
        // stale audio is repeated.
        for (long ch = 0; ch < numouts; ch++) {
            double* out = outs[ch];
            for (long i = 0; i < n; i++) out[i] = 0.0;
        }
    }
}

// Phase 3: main-thread IO rebuild. Reads the active method layout from the
// shared-memory header and resizes inlets (dsp_resize) + recreates signal
// outlets to match. Never run from the audio thread or the init thread.
void mab_tilde_rebuild_io(t_mab_tilde* x, long new_in, long new_out) {
    // dynlet-Transaction: erst die Box holen (via "#B" im Obex) und die
    // In-/Outlet-Änderungen zwischen dynlet_begin/dynlet_end klammern.
    // Ohne diese Transaction aktualisiert Max die Box erst beim nächsten
    // Patcher-Redraw (z.B. beim Verschieben des Objekts) - dieselbe Technik
    // nutzen die eingebauten [plot~] / [live.gain~] bei dynamischen Channels.
    t_object* box = NULL;
    object_obex_lookup(x, gensym("#B"), &box);
    if (box) {
        object_method(box, gensym("dynlet_begin"));
    }

    // Rebuild inlets (dsp_resize creates/frees the signal proxies)
    dsp_resize((t_pxobject*)x, new_in);

    // Phase 5: mc.mab~ Inlets müssen Multichannel-Signale zählen können.
    // Z_MC_INLETS (z_dsp.h) meldet Max, dass das Objekt die Kanalzahl
    // eingehender MC-Signale verarbeitet - ohne diesen Flag liefert Max nur
    // Kanal 1 an ein Standard-Signal-Inlet. Z_NO_INPLACE verhindert
    // In-Place-Bearbeitung (ins == outs). Dieselben Flags setzt die min-api
    // für mc_operator-Klassen (c74_min_operator_vector.h:120-128).
    if (x->is_mc) {
        x->ob.z_misc |= Z_NO_INPLACE | Z_MC_INLETS;
    }

    // Rebuild signal outlets: free the existing chain, then recreate.
    // Phase 5: mc.mab~ uses "multichannelsignal" outlets instead of "signal".
    while (x->ob.z_ob.o_outlet) {
        object_free((t_object*)x->ob.z_ob.o_outlet);
    }
    for (long i = 0; i < new_out; i++) {
        if (x->is_mc) {
            outlet_new((t_object*)x, "multichannelsignal");
        } else {
            outlet_new((t_object*)x, "signal");
        }
    }

    if (box) {
        object_method(box, gensym("dynlet_end"));
    }
}

void mab_tilde_apply_io(t_mab_tilde* x) {
    if (!x->header) {
        x->method_pending = 0;
        return;
    }

    // Model layout (used by perform64 and the method-change detection).
    long model_in = (long)x->header->channels_in;
    long model_out = (long)x->header->channels_out;
    if (model_in < 1) model_in = 1;
    if (model_out < 1) model_out = 1;
    if (model_in > MAX_CHANNELS) model_in = MAX_CHANNELS;
    if (model_out > MAX_CHANNELS) model_out = MAX_CHANNELS;

    x->channels_in = model_in;
    x->channels_out = model_out;
    strncpy(x->active_method, x->header->method, sizeof(x->active_method) - 1);
    x->active_method[sizeof(x->active_method) - 1] = '\0';
    x->active_method_id = x->header->method_id;

    // Block-Geometrie hat sich geändert: Teilblöcke der alten Methode
    // verwerfen (verhindert versetzte Frames nach einem Methoden-/Modell-Wechsel).
    x->in_pos = 0;
    x->out_pos = 0;

    // Phase 5/6: mc.mab~ hat IMMER genau 1 Multichannel-Inlet + 1 Multichannel-
    // Outlet; mcs.mab~ hat `mcs_batches` Multichannel-Inlets/-Outlets (eines pro
    // Batch). Die Kanalzahl wird über das MC-System transportiert (channel_map
    // / multichanneloutputs), nicht über die Inlet-Anzahl.
    long io_in = x->is_mcs ? x->mcs_batches : (x->is_mc ? 1 : model_in);
    long io_out = x->is_mcs ? x->mcs_batches : (x->is_mc ? 1 : model_out);

    // B4 fix: skip unnecessary IO rebuild. For methods with the same
    // inlet/outlet count as the current setup (e.g. forward: 1-in-1-out),
    // freeing and recreating outlets can corrupt Max's DSP references.
    if (io_in == x->last_io_in && io_out == x->last_io_out) {
        x->method_pending = 0;
        InterlockedExchange(&x->is_bypass, 0);
        const char* prefix = mab_tilde_prefix(x);
        post("%s: IO layout unchanged (%ld in / %ld out, method=%s)",
             prefix, io_in, io_out, x->active_method);
        return;
    }
    if (x->is_mc) {
        // Stale per-inlet counts der alten Methode verwerfen; dsp64 publiziert
        // die echten Werte nach dem Rebuild.
        for (long i = 0; i < MAX_CHANNELS; i++) {
            x->channel_map[i] = 0;
            x->header->channel_map[i] = 0;
        }
    }

    mab_tilde_rebuild_io(x, io_in, io_out);
    x->last_io_in = io_in;
    x->last_io_out = io_out;

    x->method_pending = 0;
    InterlockedExchange(&x->is_bypass, 0);
    const char* prefix = mab_tilde_prefix(x);
    post("%s: IO layout: %ld inlets, %ld outlets, method=%s (model %ld in / %ld out)",
         prefix, io_in, io_out, x->active_method, model_in, model_out);
}

// ============================================================================
// Worker-Startup
// ----------------------------------------------------------------------------
// Der eigentliche Prozess-Launch (venv-Python auflösen, CreateProcessW, Log-
// /Pipe-Redirect) liegt in worker_launch.cpp und wird von mab~, mab.info,
// mc.mab~ und mcs.mab~ gemeinsam genutzt.
// ============================================================================

extern "C" void init_worker(t_mab_tilde* x) {
    // Generate unique instance ID from process ID
    unsigned int instance_id = GetCurrentProcessId();
    
    wchar_t event_name[128];
    wchar_t shm_name[128];
    swprintf_s(event_name, L"MabReadyEvent_%08X", instance_id);
    swprintf_s(shm_name, L"MabSharedMem_%08X", instance_id);

    x->ready_event = CreateEventW(NULL, TRUE, FALSE, event_name);

    // A4: input-ready event to wake Python immediately when a block is ready.
    wchar_t input_event_name[128];
    swprintf_s(input_event_name, L"MabInputReadyEvent_%08X", instance_id);
    x->input_ready_event = CreateEventW(NULL, FALSE, FALSE, input_event_name);

    // --- Worker portabel starten (Pfad-Auflösung im Launch-Helper) ---
    char shm_name_utf8[256];
    WideCharToMultiByte(CP_UTF8, 0, shm_name, -1, shm_name_utf8,
                        (int)sizeof(shm_name_utf8), NULL, NULL);

    char argbuf[2048];
    // Phase 6: n_batches (nach gpu) wird für mcs.mab~ übergeben; mab~/mc.mab~
    // senden immer 1 (Python-argparse: model method bufsize gpu n_batches
    // shm_name instance_id num_channels cores).
    snprintf(argbuf, sizeof(argbuf), "\"%s\" \"%s\" %ld %d %ld \"%s\" %u %ld %ld",
             x->model_path, x->method_name, x->buffer_size,
             (int)x->gpu, x->is_mcs ? x->mcs_batches : 1,
             shm_name_utf8, instance_id, x->num_channels,
             x->cores);

    WorkerProcess wp;
    worker_launch(argbuf, false, &wp);
    const char* prefix = mab_tilde_prefix(x);
    if (!wp.process) {
        post("%s: Failed to launch Python process. Running in bypass.", prefix);
        InterlockedExchange(&x->is_bypass, 1);
        return;
    }

    x->python_process = wp.process;

    // Wait for Python to signal the ready event.
    // Läuft im Hintergrund-Thread (init_worker_thread) -> kein OS-Lock im
    // Audio-Thread. 10 s, weil der erste PyTorch-Import Sekunden dauern kann.
    DWORD waitResult = WaitForSingleObject(x->ready_event, 10000); 
    if (waitResult == WAIT_OBJECT_0) {
        x->hMapFile = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, shm_name);
        if (x->hMapFile) {
            void* pBuf = MapViewOfFile(x->hMapFile, FILE_MAP_ALL_ACCESS, 0, 0, 0);
            if (pBuf) {
                SharedMemoryHeader* header = (SharedMemoryHeader*)pBuf;
                if (header->magic == 0x4D414254) { // 'MABT'
                    x->header = header;
                    x->p_input = (float*)((char*)pBuf + header->input_offset);
                    x->p_output = (float*)((char*)pBuf + header->output_offset);
                    x->p_control = (ControlRingBuffer*)((char*)pBuf + header->control_offset);

                    // A1: double-buffer indices start at 0.
                    header->input_buffer_index = 0;
                    header->output_buffer_index = 0;

                    // Phase 5: MC channel map starts empty; mc_mab_tilde_dsp64
                    // publishes the real per-inlet counts on the next DSP compile.
                    for (long i = 0; i < MAX_CHANNELS; i++) {
                        header->channel_map[i] = 0;
                    }
                    
                    InterlockedExchange(&x->is_bypass, 0); // Disable bypass
                    // Schedule IO rebuild BEFORE marking ready so
                    // perform64 cannot fire with stale channels_in/out.
                    x->in_pos = 0;
                    x->out_pos = 0;
                    x->method_pending = 1;
                    qelem_set(x->io_qelem);
                    InterlockedExchange(&x->is_ready, 1);  // Mark as ready
                    // A2: start periodic crash monitoring on main thread.
                    clock_fdelay(x->crash_clock, 100.0);
                    post("%s: Python worker ready, shared memory mapped successfully.", prefix);
                } else {
                    post("%s error: Invalid shared memory header magic.", prefix);
                    UnmapViewOfFile(pBuf);
                }
            } else {
                post("%s error: Failed to map shared memory view.", prefix);
            }
        } else {
            post("%s error: Failed to open shared memory mapping.", prefix);
        }
    } else {
        post("%s error: Timeout waiting for Python worker. Check mab_worker.log for details.", prefix);
    }
}

void init_worker_thread(t_mab_tilde* x) {
    init_worker(x);
}

// ============================================================================
// Phase 1.7: Message Handlers
// ============================================================================

// Lock-free SPSC enqueue into the control ring buffer (C++ = producer).
// Returns true if the message was written, false when the ring is full or the
// worker is not connected. Never blocks.
static bool mab_enqueue_control(t_mab_tilde* x, const char* msg) {
    if (!x || !x->is_ready || !x->header || !x->p_control || !msg)
        return false;

    long next_head = InterlockedIncrement(&x->p_control->head);
    long head = next_head - 1;
    long tail = x->p_control->tail;

    if (head - tail < CONTROL_RING_SIZE - 1) {
        long idx = head & (CONTROL_RING_SIZE - 1);
        strncpy(x->p_control->messages[idx], msg, CONTROL_MSG_SIZE - 1);
        x->p_control->messages[idx][CONTROL_MSG_SIZE - 1] = '\0';
        return true;
    }
    // Ring full: roll back the head increment
    InterlockedExchange(&x->p_control->head, head);
    return false;
}

void mab_tilde_enable(t_mab_tilde* x, long flag) {
    if (flag) {
        x->is_bypass = 0;
        post("mab~: Audio processing enabled");
    } else {
        x->is_bypass = 1;
        post("mab~: Audio processing disabled (bypass)");
    }
}

void mab_tilde_gpu(t_mab_tilde* x, long flag) {
    x->gpu = flag ? 1 : 0;
    // B5 fix: async GPU reload via Python must not race with perform64.
    // Set bypass to stop audio processing while the worker reloads,
    // then schedule a timer to clear bypass (Python reload takes ~1-3 s).
    char msg_buf[CONTROL_MSG_SIZE];
    snprintf(msg_buf, sizeof(msg_buf), "gpu %d", x->gpu);
    if (mab_enqueue_control(x, msg_buf)) {
        x->is_bypass = 1;
        // Reset active_method_id so perform64 re-detects the
        // (potentially changed) method layout after the reload.
        x->active_method_id = 0;
        clock_fdelay(x->gpu_reload_clock, 3000.0);
        post("mab~: GPU mode set to %ld (worker reloading model, 3 s bypass)", flag);
    } else {
        post("mab~: GPU mode set to %ld (will apply on next load)", flag);
    }
}

void mab_tilde_gpu_reload_done(t_mab_tilde* x) {
    if (!x->header) return;
    if (x->header->method_id != x->active_method_id) {
        // Python wrote new method layout → queue IO rebuild
        x->method_pending = 1;
        qelem_set(x->io_qelem);
    }
    // Bypass is cleared in mab_tilde_apply_io after IO rebuild,
    // or here if no rebuild is needed.
    if (!x->method_pending) {
        InterlockedExchange(&x->is_bypass, 0);
    }
}

void mab_tilde_reload(t_mab_tilde* x, t_symbol* s) {
    // A2: stop crash monitoring while the old worker is being torn down
    if (x->crash_clock) {
        clock_unset(x->crash_clock);
    }

    // 1. Tell current process to shut down and unblock wait events
    if (x->header) {
        InterlockedExchange(&x->header->shutdown_flag, 1);
    }
    if (x->ready_event) {
        SetEvent(x->ready_event);
    }

    // 2. Safely join and delete the existing thread FIRST (if it exists)
    if (x->init_thread) {
        if (x->init_thread->joinable()) {
            x->init_thread->join();
        }
        delete x->init_thread;
        x->init_thread = nullptr;
    }

    // 3. Stop current Python process if still running
    if (x->python_process) {
        DWORD waitResult = WaitForSingleObject(x->python_process, 500);
        if (waitResult == WAIT_TIMEOUT) {
            TerminateProcess(x->python_process, 1);
        }
        CloseHandle(x->python_process);
        x->python_process = nullptr;
    }
    
    // 4. Cleanup shared memory and handles
    if (x->header) {
        UnmapViewOfFile(x->header);
        x->header = nullptr;
        x->p_input = nullptr;
        x->p_output = nullptr;
        x->p_control = nullptr;
    }
    if (x->hMapFile) {
        CloseHandle(x->hMapFile);
        x->hMapFile = nullptr;
    }
    if (x->ready_event) {
        CloseHandle(x->ready_event);
        x->ready_event = nullptr;
    }
    if (x->input_ready_event) {
        CloseHandle(x->input_ready_event);
        x->input_ready_event = nullptr;
    }

    // 5. Reset method-aware layout state; the fresh worker handshake will
    //    trigger a rebuild via qelem with the new method's channels.
    x->active_method[0] = '\0';
    x->active_method_id = 0;
    x->channels_in = 1;
    x->channels_out = 1;
    x->in_pos = 0;
    x->out_pos = 0;
    x->method_pending = 0;
    
    // 6. Update model path if provided
    if (s && s->s_name) {
        strncpy(x->model_path, s->s_name, sizeof(x->model_path) - 1);
        char resolved[MAX_PATH];
        if (mab_resolve_model_path(x->model_path, resolved, sizeof(resolved)))
            strncpy(x->model_path, resolved, sizeof(x->model_path) - 1);
    }
    
    // 7. Reset state and start a fresh worker
    x->is_ready = 0;
    x->is_bypass = 1;
    
    x->init_thread = new std::thread(init_worker_thread, x);
    
    post("mab~: Reloaded with model %s", s && s->s_name ? s->s_name : "same");
}

void mab_tilde_dump(t_mab_tilde* x) {
    post("mab~: Model path: %s", x->model_path);
    post("mab~: Method: %s", x->active_method[0] ? x->active_method : x->method_name);
    post("mab~: Buffer size: %ld", x->buffer_size);
    post("mab~: GPU mode: %ld", x->gpu);
    post("mab~: Channels: %ld", x->num_channels);
    if (x->header) {
        post("mab~: Layout: %lu inlets, %lu outlets, block_size=%lu, in_ratio=%lu, out_ratio=%lu, latent=%lu",
             (unsigned long)x->header->channels_in,
             (unsigned long)x->header->channels_out,
             (unsigned long)x->header->block_size,
             (unsigned long)x->header->input_ratio,
             (unsigned long)x->header->output_ratio,
             (unsigned long)x->header->latent_size);
    }
    post("mab~: Ready: %ld", x->is_ready);
    post("mab~: Bypass: %ld", x->is_bypass);

    // nn_tilde-Parität P2: zusätzlich die volle Modell-Metadaten aus dem Worker
    // (Methoden, Params, Attribute) ins Log schreiben lassen.
    if (mab_enqueue_control(x, "dump")) {
        post("mab~: requesting worker model info...");
    }
}

void mab_tilde_set(t_mab_tilde* x, t_symbol* s, long argc, t_atom* argv) {
    if (argc < 2) {
        error("mab~: set requires attribute name and value");
        return;
    }
    
    t_symbol* attr = atom_getsym(argv);
    
    if (!attr || !attr->s_name) return;

    if (strcmp(attr->s_name, "gpu") == 0) {
        mab_tilde_gpu(x, atom_getlong(argv + 1));
        return;
    } else if (strcmp(attr->s_name, "buffer_size") == 0) {
        x->buffer_size = atom_getlong(argv + 1);
        post("mab~: Buffer size set to %ld", x->buffer_size);
        return;
    } else if (strcmp(attr->s_name, "channels") == 0) {
        x->num_channels = atom_getlong(argv + 1);
        post("mab~: Channels set to %ld", x->num_channels);
        return;
    }

    // nn_tilde-Parität P1: alle übrigen Attribute an den Worker weiterreichen,
    // der sie per Typ-Koerzierung auf das Modell anwendet (setattr).
    char msg_buf[CONTROL_MSG_SIZE];
    int written = snprintf(msg_buf, sizeof(msg_buf), "set %s", attr->s_name);
    for (long i = 1; i < argc && written < (int)sizeof(msg_buf) - 64; i++) {
        if (argv[i].a_type == A_SYM) {
            written += snprintf(msg_buf + written, sizeof(msg_buf) - written,
                                " %s", atom_getsym(argv + i)->s_name);
        } else if (argv[i].a_type == A_LONG) {
            written += snprintf(msg_buf + written, sizeof(msg_buf) - written,
                                " %ld", (long)atom_getlong(argv + i));
        } else if (argv[i].a_type == A_FLOAT) {
            written += snprintf(msg_buf + written, sizeof(msg_buf) - written,
                                " %g", atom_getfloat(argv + i));
        }
    }
    if (mab_enqueue_control(x, msg_buf)) {
        post("mab~: forwarded attribute: %s", msg_buf);
    } else {
        post("mab~: (not ready) set %s", attr->s_name);
    }
}

void mab_tilde_get(t_mab_tilde* x, t_symbol* s) {
    if (!s || !s->s_name) return;

    if (strcmp(s->s_name, "gpu") == 0) {
        post("mab~: gpu = %ld", x->gpu);
    } else if (strcmp(s->s_name, "buffer_size") == 0) {
        post("mab~: buffer_size = %ld", x->buffer_size);
    } else if (strcmp(s->s_name, "channels") == 0) {
        post("mab~: channels = %ld", x->num_channels);
    } else if (strcmp(s->s_name, "ready") == 0) {
        post("mab~: ready = %ld", x->is_ready);
    } else if (strcmp(s->s_name, "method") == 0) {
        post("mab~: method = %s", x->active_method[0] ? x->active_method : x->method_name);
    } else if (strcmp(s->s_name, "model") == 0) {
        post("mab~: model = %s", x->model_path);
    } else {
        // nn_tilde-Parität P1: Modell-Attribute an den Worker weiterreichen
        // (Antwort erscheint im Worker-Log).
        char msg_buf[CONTROL_MSG_SIZE];
        snprintf(msg_buf, sizeof(msg_buf), "get %s", s->s_name);
        if (mab_enqueue_control(x, msg_buf)) {
            post("mab~: forwarded get: %s", s->s_name);
        } else {
            post("mab~: (not ready) get %s", s->s_name);
        }
    }
}

void mab_tilde_method(t_mab_tilde* x, t_symbol* s, long argc, t_atom* argv) {
    // Forward the method switch to Python via the control ring buffer. The
    // worker updates header->method + channel layout; perform64 detects the
    // change and schedules the main-thread IO rebuild.
    if (!s || !s->s_name) return;

    char msg_buf[CONTROL_MSG_SIZE];
    snprintf(msg_buf, sizeof(msg_buf), "method %s", s->s_name);

    if (mab_enqueue_control(x, msg_buf)) {
        post("mab~: switching method: %s", s->s_name);
    } else {
        post("mab~: (not ready) method %s", s->s_name);
    }
}

void mab_tilde_load(t_mab_tilde* x, t_symbol* s) {
    if (s && s->s_name) {
        strncpy(x->model_path, s->s_name, sizeof(x->model_path) - 1);
        char resolved[MAX_PATH];
        if (mab_resolve_model_path(x->model_path, resolved, sizeof(resolved)))
            strncpy(x->model_path, resolved, sizeof(x->model_path) - 1);
        post("mab~: Model path set to %s. Triggering reload...", s->s_name);
        mab_tilde_reload(x, s);
    } else {
        error("mab~: load requires a valid model path argument");
    }
}

// Phase 1.7: Anything message forwarding to Python via lock-free ring buffer
void mab_tilde_anything(t_mab_tilde* x, t_symbol* s, long argc, t_atom* argv) {
    // Forward any unrecognized messages to Python via control ring buffer
    if (!x->is_ready || !x->header || !x->p_control) {
        // Not ready - just print the message
        char msg_str[512];
        snprintf(msg_str, sizeof(msg_str), "mab~: (not ready) %s", s ? s->s_name : "unknown");
        post("%s", msg_str);
        return;
    }
    
    // Build message string for Python
    // Format: "message_name arg1 arg2 ..."
    char msg_buf[CONTROL_MSG_SIZE];
    int written = snprintf(msg_buf, sizeof(msg_buf), "%s", s ? s->s_name : "unknown");
    
    for (long i = 0; i < argc && written < (int)sizeof(msg_buf) - 64; i++) {
        if (argv[i].a_type == A_SYM) {
            written += snprintf(msg_buf + written, sizeof(msg_buf) - written, " %s", atom_getsym(argv + i)->s_name);
        } else if (argv[i].a_type == A_LONG) {
            written += snprintf(msg_buf + written, sizeof(msg_buf) - written, " %ld", (long)atom_getlong(argv + i));
        } else if (argv[i].a_type == A_FLOAT) {
            written += snprintf(msg_buf + written, sizeof(msg_buf) - written, " %f", atom_getfloat(argv + i));
        }
    }
    
    // Enqueue message into lock-free ring buffer (non-blocking)
    if (mab_enqueue_control(x, msg_buf)) {
        post("mab~: forwarded message: %s", msg_buf);
    } else {
        post("mab~: (not ready / ring full) %s", msg_buf);
    }
}

// ============================================================================
// Phase 5: mc.mab~ (Multichannel) Implementation
// ============================================================================

// mc.mab~ constructor. Shares the same t_mab_tilde struct with mab~ but sets
// is_mc=1 for multichannel signal inlets/outlets and MC-specific callbacks.
void* mc_mab_tilde_new(t_symbol* s, long argc, t_atom* argv) {
    t_mab_tilde* x = (t_mab_tilde*)object_alloc(mc_mab_tilde_class);
    if (!x) return nullptr;

    // Use dsp_setup with 1 inlet initially (will be resized after worker connects)
    dsp_setup((t_pxobject*)x, 1);
    // Phase 5: Multichannel-Fähigkeit aktivieren (Z_MC_INLETS = Kanalzahl der
    // eingehenden MC-Signale zählen; Z_NO_INPLACE = kein In-Place-Processing).
    // Ohne Z_MC_INLETS liefert Max nur Kanal 1 an den Inlet.
    x->ob.z_misc |= Z_NO_INPLACE | Z_MC_INLETS;
    outlet_new(x, "multichannelsignal");

    // Initialize variables (same as mab~)
    x->is_ready = 0;
    x->is_bypass = 1;
    x->num_channels = 1;

    x->init_thread = nullptr;
    x->python_process = nullptr;
    x->ready_event = nullptr;
    x->input_ready_event = nullptr;
    x->hMapFile = nullptr;
    x->header = nullptr;
    x->p_input = nullptr;
    x->p_output = nullptr;
    x->p_control = nullptr;

    x->model_path[0] = '\0';
    x->method_name[0] = '\0';
    x->buffer_size = 512;
    x->gpu = 0;
    x->cores = 2;   // Default: 2 PyTorch-Inferenz-Threads (mc.mab~)
    x->control_size = 0;
    memset(x->control_buffer, 0, sizeof(x->control_buffer));

    buffer_manager_init(&x->buffer_mgr);

    // Phase 3: method-aware IO state
    x->active_method[0] = '\0';
    x->active_method_id = 0;
    x->channels_in = 1;
    x->channels_out = 1;
    x->in_pos = 0;
    x->out_pos = 0;
    x->method_pending = 0;
    x->io_qelem = qelem_new(x, (method)mab_tilde_apply_io);
    x->crash_clock = clock_new(x, (method)mab_tilde_check_crash);
    x->gpu_reload_clock = clock_new(x, (method)mab_tilde_gpu_reload_done);

    // Phase 5: MC fields (mc.mab~ mode: is_mc=1)
    x->is_mc = 1;
    x->n_batches = 0;  // 0 = auto-detect from channel_map
    for (long i = 0; i < 16; i++) x->channel_map[i] = 0;
    x->last_io_in = 1;   // dsp_setup(x,1) + outlet_new in constructor
    x->last_io_out = 1;

    // Parse arguments
    long void_mode = 0;
    if (argc >= 1) {
        t_symbol* first = atom_getsym(argv);
        if (first && first->s_name && strcmp(first->s_name, "void") == 0)
            void_mode = 1;
    }

    if (argc >= 1 && !void_mode) {
        t_symbol* model_sym = atom_getsym(argv);
        if (model_sym && model_sym->s_name) {
            strncpy(x->model_path, model_sym->s_name, sizeof(x->model_path) - 1);
            char resolved[MAX_PATH];
            if (mab_resolve_model_path(x->model_path, resolved, sizeof(resolved)))
                strncpy(x->model_path, resolved, sizeof(x->model_path) - 1);
        }
    }
    // B3 fix: auto-detect if user skipped the optional method argument.
    bool has_method = false;
    if (argc >= 2 && !void_mode) {
        if (argv[1].a_type != A_LONG && argv[1].a_type != A_FLOAT) {
            has_method = true;
        }
    }

    if (has_method) {
        t_symbol* method_sym = atom_getsym(argv + 1);
        if (method_sym && method_sym->s_name) {
            strncpy(x->method_name, method_sym->s_name, sizeof(x->method_name) - 1);
        }
    }

    long off = has_method ? 2 : 1;
    if (argc > off && !void_mode)     x->buffer_size = atom_getlong(argv + off);
    if (argc > off+1 && !void_mode)   x->gpu = atom_getlong(argv + off+1);
    if (argc > off+2 && !void_mode)   x->num_channels = atom_getlong(argv + off+2);
    if (argc > off+3 && !void_mode) {
        x->cores = atom_getlong(argv + off+3);
        if (x->cores < 1) x->cores = 1;
        if (x->cores > 64) x->cores = 64;
    }

    if (void_mode) {
        // mc.mab~ void <inlets> <outlets> <bufsize>
        long n_in = (argc >= 2) ? atom_getlong(argv + 1) : 1;
        long n_out = (argc >= 3) ? atom_getlong(argv + 2) : 1;
        if (argc >= 4) x->buffer_size = atom_getlong(argv + 3);
        if (n_in < 1) n_in = 1;
        if (n_out < 1) n_out = 1;
        if (n_in > MAX_CHANNELS) n_in = MAX_CHANNELS;
        if (n_out > MAX_CHANNELS) n_out = MAX_CHANNELS;
        x->channels_in = n_in;
        x->channels_out = n_out;
        x->num_channels = n_out;
        // In MC void mode, each inlet/outlet is multichannel with 1 channel
        for (long i = 0; i < n_in; i++) x->channel_map[i] = 1;
        strncpy(x->active_method, "forward", sizeof(x->active_method) - 1);
        x->active_method[sizeof(x->active_method) - 1] = '\0';
        x->active_method_id = 0;

        // Direct IO setup (main thread, no qelem needed)
        mab_tilde_rebuild_io(x, n_in, n_out);
        post("mc.mab~: void mode: %ld inlets, %ld outlets, buffer_size=%ld",
             n_in, n_out, x->buffer_size);
        return x;
    }

    // If a model path was provided, start the worker immediately.
    if (x->model_path[0] != '\0') {
        x->init_thread = new std::thread(init_worker_thread, x);
    } else {
        post("mc.mab~: Created in 'no model' state. Use [load <model>] to start.");
    }

    return x;
}

// mc.mab~: dsp64 callback. Reads the channel count from the Max DSP chain to
// populate channel_map. The `count` array has one entry per inlet telling us
// how many channels are connected. We store these in channel_map, publish them
// to the shared-memory header (Phase 5, 5.3) and register the MC perform.
// IMPORTANT: x->channels_in (the model's declared input count) is deliberately
// NOT overwritten here - it stays in sync with header->channels_in so the
// method-change detection in perform64 never triggers a rebuild loop.
void mc_mab_tilde_dsp64(t_mab_tilde* x, t_object* dsp64, short* count, double samplerate, long maxvectorsize, long flags) {
    // z_in = current number of signal inlets (1 in mc.mab~ mode).
    long n_inlets = x->ob.z_in;
    if (n_inlets < 1) n_inlets = 1;
    if (n_inlets > MAX_CHANNELS) n_inlets = MAX_CHANNELS;

    long total_in = 0;
    for (long i = 0; i < n_inlets; i++) {
        long ch = (count && i < n_inlets) ? (long)count[i] : 1;
        if (ch < 1) ch = 1;
        if (ch > MAX_CHANNELS) ch = MAX_CHANNELS;
        x->channel_map[i] = ch;
        total_in += ch;
    }
    // Stale entries beyond the current inlet count are cleared so Python sees
    // exactly the connected inlets.
    for (long i = n_inlets; i < MAX_CHANNELS; i++) x->channel_map[i] = 0;

    // Publish the per-inlet channel map to the worker.
    if (x->header) {
        for (long i = 0; i < MAX_CHANNELS; i++) {
            x->header->channel_map[i] = (uint32_t)x->channel_map[i];
        }
    }

    // Läuft nur bei DSP-Kompilierung (nicht pro Tick): zeigt die tatsächlich
    // verbundenen Kanalzahlen - wichtig für die MC-Verifikation (5.8).
    if (total_in != x->channels_in) {
        post("mc.mab~: DSP: %ld inlet(s), %ld channel(s) connected "
             "(model expects %ld). Unconnected model channels are silenced.",
             n_inlets, total_in, x->channels_in);
    }

    object_method(dsp64, gensym("dsp_add64"), x, mc_mab_tilde_perform64, 0, NULL);
}

// mc.mab~: MC-aware perform function. Uses the same block_accumulator logic
// as mab~ but with the channel counts from the model layout (x->channels_in /
// x->channels_out). Missing input channels (fewer connected than the model
// declares) are zero-padded by block_accumulate_write; extra outlet channels
// (e.g. `chans` larger than the model output) are silenced below.
void mc_mab_tilde_perform64(t_mab_tilde* x, t_object* dsp64, double** ins, long numins, double** outs, long numouts, long sampleframes, long flags, void* userparam) {
    long n = sampleframes;
    if (n < 0) n = 0;

    // Bypass mode: pass through as many channels as available (MC-friendly).
    if (!x->is_ready || x->is_bypass || !x->header) {
        long pass = (numins < numouts) ? numins : numouts;
        for (long ch = 0; ch < numouts; ch++) {
            double* out = outs[ch];
            double* in = (ch < pass && ins[ch]) ? ins[ch] : nullptr;
            for (long i = 0; i < n; i++) out[i] = in ? in[i] : 0.0;
        }
        return;
    }

    const long blk = (long)x->header->block_size;
    if (blk < 1) {
        for (long ch = 0; ch < numouts; ch++)
            for (long i = 0; i < n; i++) outs[ch][i] = 0.0;
        return;
    }

    // Model-declared channel counts (stable; never the per-inlet wiring).
    const long channels_in = x->channels_in;
    const long channels_out = x->channels_out;

    // Method-change detection (same as mab~)
    if (!x->method_pending &&
        (x->header->method_id != x->active_method_id ||
         (long)x->header->channels_in != x->channels_in ||
         (long)x->header->channels_out != x->channels_out)) {
        x->method_pending = 1;
        qelem_set(x->io_qelem);
    }

    const size_t input_buffer_stride = (size_t)channels_in * (size_t)blk;
    const size_t output_buffer_stride = (size_t)channels_out * (size_t)blk;

    // A1: Double-buffered input. block_accumulate_write zero-pads rows for
    // channels that have no connected input (ch >= numins), so the model
    // always receives a full [channels_in][block_size] block.
    if (x->header->is_input_ready == 0) {
        uint32_t in_idx = x->header->input_buffer_index & 1;
        float* input_ptr = x->p_input + in_idx * input_buffer_stride;
        if (block_accumulate_write(input_ptr, channels_in, blk, n,
                                   ins, numins, x->in_pos)) {
            x->header->input_buffer_index = 1 - in_idx;
            InterlockedExchange(&x->header->is_input_ready, 1);
            if (x->input_ready_event) {
                SetEvent(x->input_ready_event);
            }
        }
    }

    // A1: Double-buffered output. Drain only the channels that actually have
    // outlets (numouts); remaining outlet channels are silenced.
    if (x->header->is_output_ready == 1) {
        uint32_t out_idx = x->header->output_buffer_index & 1;
        float* output_ptr = x->p_output + out_idx * output_buffer_stride;
        long read_ch = channels_out;
        if (read_ch > numouts) read_ch = numouts;
        if (read_ch < 1) read_ch = 1;
        if (block_accumulate_read(output_ptr, read_ch, blk, n,
                                  outs, numouts, x->out_pos)) {
            InterlockedExchange(&x->header->is_output_ready, 0);
            x->header->output_buffer_index = 1 - out_idx;
        }
        // Outlets beyond the model's channel count: silence (no stale data).
        for (long ch = read_ch; ch < numouts; ch++) {
            double* out = outs[ch];
            if (!out) continue;
            for (long i = 0; i < n; i++) out[i] = 0.0;
        }
    } else {
        for (long ch = 0; ch < numouts; ch++) {
            double* out = outs[ch];
            for (long i = 0; i < n; i++) out[i] = 0.0;
        }
    }
}

// multichanneloutputs callback: called by Max to determine how many output
// channels a given outlet produces. Returns the fixed count from `chans`
// attribute (n_batches) if set, otherwise returns channels_out.
long mc_multichanneloutputs(t_mab_tilde* x, long index, long count) {
    if (x->n_batches > 0) {
        return x->n_batches;
    }
    return x->channels_out;
}

// inputchanged callback: called by Max when the channel count on an inlet
// changes. Updates the channel_map entry for this inlet index and publishes
// it to the worker (Phase 5, 5.3). x->channels_in (model layout) is untouched.
long mc_inputchanged(t_mab_tilde* x, long index, long count) {
    if (index < 0 || index >= 16) return 0;
    if (count < 1) count = 1;
    if (count > MAX_CHANNELS) count = MAX_CHANNELS;

    if (x->channel_map[index] != count) {
        x->channel_map[index] = count;
        if (x->header) {
            x->header->channel_map[index] = (uint32_t)count;
        }
        long total = 0;
        for (long i = 0; i < 16; i++) total += x->channel_map[i];
        post("mc.mab~: inlet %ld channel count changed to %ld (total in=%ld)",
             index, count, total);
    }
    return 1;
}

// chans <n>: set a fixed number of output channels per (mc/mcs) outlet
// (nn_tilde-Parität P8/P9). When set to 0, output channels are auto-detected
// from the model layout. Shared by mc.mab~ and mcs.mab~.
void mc_mab_tilde_chans(t_mab_tilde* x, long n) {
    if (n < 0) n = 0;
    if (n > MAX_CHANNELS * 16) n = MAX_CHANNELS * 16;
    x->n_batches = n;
    post("%s: chans set to %ld", mab_tilde_prefix(x), n);
}

// ============================================================================
// Phase 6: mcs.mab~ (Batched Multichannel) Implementation
// ============================================================================
//
// mcs.mab~ erweitert mc.mab~ um `mcs_batches` parallele Batch-Inlets/-Outlets
// (nn_tilde-Parität P9): Jedes Batch-Inlet ist ein Multichannel-Inlet mit
// `channel_map[b]` Kanälen (Modell-Layout: `channels_in` pro Batch), jedes
// Batch-Outlet liefert `channels_out` (oder `chans`) Kanäle.
//
// Shared-Memory-Layout (6.3): batch-major [n_batches x channels x block_size].
// C++ schreibt Zeile `b*ci + c` (Batch b, Kanal c), Python viewed
// `(n_batches, ci, block_size)`. Abweichend von nn_tildes interleaved
// `c*B + b` - bewusste Design-Entscheidung (checklist.md 6.0).

// mcs.mab~ constructor. Shares the same t_mab_tilde struct and worker with
// mab~/mc.mab~; sets is_mcs=1 (and is_mc=1 for MC outlets / Z_MC_INLETS).
void* mcs_mab_tilde_new(t_symbol* s, long argc, t_atom* argv) {
    t_mab_tilde* x = (t_mab_tilde*)object_alloc(mcs_mab_tilde_class);
    if (!x) return nullptr;

    // Phase 6: mcs.mab~ hat `mcs_batches` Multichannel-Inlets/-Outlets.
    // Start mit 1 Inlet/Outlet; apply_io baut nach Worker-Connect um.
    dsp_setup((t_pxobject*)x, 1);
    // Z_MC_INLETS = Kanalzahl eingehender MC-Signale zählen (wie mc.mab~).
    x->ob.z_misc |= Z_NO_INPLACE | Z_MC_INLETS;
    outlet_new(x, "multichannelsignal");

    // Initialize variables (same as mab~/mc.mab~)
    x->is_ready = 0;
    x->is_bypass = 1;
    x->num_channels = 1;

    x->init_thread = nullptr;
    x->python_process = nullptr;
    x->ready_event = nullptr;
    x->input_ready_event = nullptr;
    x->hMapFile = nullptr;
    x->header = nullptr;
    x->p_input = nullptr;
    x->p_output = nullptr;
    x->p_control = nullptr;

    x->model_path[0] = '\0';
    x->method_name[0] = '\0';
    x->buffer_size = 512;
    x->gpu = 0;
    x->cores = 2;   // Default: 2 PyTorch-Inferenz-Threads (mcs.mab~)
    x->control_size = 0;
    memset(x->control_buffer, 0, sizeof(x->control_buffer));

    buffer_manager_init(&x->buffer_mgr);

    // Phase 3: method-aware IO state
    x->active_method[0] = '\0';
    x->active_method_id = 0;
    x->channels_in = 1;
    x->channels_out = 1;
    x->in_pos = 0;
    x->out_pos = 0;
    x->method_pending = 0;
    x->io_qelem = qelem_new(x, (method)mab_tilde_apply_io);
    x->crash_clock = clock_new(x, (method)mab_tilde_check_crash);
    x->gpu_reload_clock = clock_new(x, (method)mab_tilde_gpu_reload_done);

    // Phase 6: mcs fields (mcs.mab~ mode: is_mcs=1, is_mc=1)
    x->is_mcs = 1;
    x->is_mc = 1;
    x->mcs_batches = 1;  // 1 = single batch (mc-like behaviour)
    x->n_batches = 0;    // `chans` per-outlet channel count (0 = auto)
    for (long i = 0; i < 16; i++) x->channel_map[i] = 0;
    x->last_io_in = 1;   // dsp_setup(x,1) + outlet_new in constructor
    x->last_io_out = 1;

    // Parse arguments. mcs.mab~ uses its own order (nn_tilde-Parität P9):
    //   [mcs.mab~ model method n_batches bufsize gpu cores]
    //   [mcs.mab~ void n_batches bufsize]
    // B3 fix: method is optional; auto-detect if user skipped it.
    long void_mode = 0;
    if (argc >= 1) {
        t_symbol* first = atom_getsym(argv);
        if (first && first->s_name && strcmp(first->s_name, "void") == 0)
            void_mode = 1;
    }

    if (void_mode) {
        // mcs.mab~ void <n_batches> <bufsize>
        long nb = (argc >= 2) ? atom_getlong(argv + 1) : 1;
        if (argc >= 3) x->buffer_size = atom_getlong(argv + 2);
        if (nb < 1) nb = 1;
        if (nb > MAX_CHANNELS) nb = MAX_CHANNELS;
        x->mcs_batches = nb;
        x->channels_in = 1;
        x->channels_out = 1;
        x->num_channels = 1;
        // In void mode each batch inlet/outlet is multichannel with 1 channel
        for (long i = 0; i < nb; i++) x->channel_map[i] = 1;
        strncpy(x->active_method, "forward", sizeof(x->active_method) - 1);
        x->active_method[sizeof(x->active_method) - 1] = '\0';
        x->active_method_id = 0;

        // Direct IO setup (main thread, no qelem needed)
        mab_tilde_rebuild_io(x, nb, nb);
        post("mcs.mab~: void mode: %ld batch inlets/outlets, buffer_size=%ld",
             nb, x->buffer_size);
        return x;
    }

    if (argc >= 1) {
        t_symbol* model_sym = atom_getsym(argv);
        if (model_sym && model_sym->s_name) {
            strncpy(x->model_path, model_sym->s_name, sizeof(x->model_path) - 1);
            char resolved[MAX_PATH];
            if (mab_resolve_model_path(x->model_path, resolved, sizeof(resolved)))
                strncpy(x->model_path, resolved, sizeof(x->model_path) - 1);
        }
    }
    // B3 fix: auto-detect if user skipped the optional method argument.
    bool has_method = false;
    if (argc >= 2) {
        if (argv[1].a_type != A_LONG && argv[1].a_type != A_FLOAT) {
            has_method = true;
        }
    }

    if (has_method) {
        t_symbol* method_sym = atom_getsym(argv + 1);
        if (method_sym && method_sym->s_name) {
            strncpy(x->method_name, method_sym->s_name, sizeof(x->method_name) - 1);
        }
    }

    long off = has_method ? 2 : 1;
    if (argc > off) {
        long nb = atom_getlong(argv + off);
        if (nb < 1) nb = 1;
        if (nb > MAX_CHANNELS) nb = MAX_CHANNELS;
        x->mcs_batches = nb;
    }
    if (argc > off+1) x->buffer_size = atom_getlong(argv + off+1);
    if (argc > off+2) x->gpu = atom_getlong(argv + off+2);
    if (argc > off+3) {
        x->cores = atom_getlong(argv + off+3);
        if (x->cores < 1) x->cores = 1;
        if (x->cores > 64) x->cores = 64;
    }

    // If a model path was provided, start the worker immediately.
    if (x->model_path[0] != '\0') {
        x->init_thread = new std::thread(init_worker_thread, x);
    } else {
        post("mcs.mab~: Created in 'no model' state. Use [load <model>] to start.");
    }

    return x;
}

// mcs.mab~: dsp64 callback. Reads the channel count per batch inlet from the
// Max DSP chain and publishes the map to the worker. `count[i]` = channels
// connected to batch inlet i. x->channels_in (model layout) stays untouched.
void mcs_mab_tilde_dsp64(t_mab_tilde* x, t_object* dsp64, short* count, double samplerate, long maxvectorsize, long flags) {
    long n_inlets = x->mcs_batches;
    if (n_inlets < 1) n_inlets = 1;
    if (n_inlets > MAX_CHANNELS) n_inlets = MAX_CHANNELS;

    long total_in = 0;
    for (long i = 0; i < n_inlets; i++) {
        long ch = (count && i < n_inlets) ? (long)count[i] : 1;
        if (ch < 1) ch = 1;
        if (ch > MAX_CHANNELS) ch = MAX_CHANNELS;
        x->channel_map[i] = ch;
        total_in += ch;
    }
    // Stale entries beyond the current batch count are cleared.
    for (long i = n_inlets; i < MAX_CHANNELS; i++) x->channel_map[i] = 0;

    if (x->header) {
        for (long i = 0; i < MAX_CHANNELS; i++) {
            x->header->channel_map[i] = (uint32_t)x->channel_map[i];
        }
    }

    if (total_in != x->channels_in * n_inlets) {
        post("mcs.mab~: DSP: %ld batch inlet(s), %ld channel(s) connected "
             "(model expects %ld per batch). Unconnected channels are silenced.",
             n_inlets, total_in, x->channels_in);
    }

    object_method(dsp64, gensym("dsp_add64"), x, mcs_mab_tilde_perform64, 0, NULL);
}

// mcs.mab~: MC-aware batched perform function. Wires the flat per-inlet
// channel arrays from Max into the batch-major shared-memory rows `b*ci+c`
// (input) and back from rows `b*co+c` into the per-batch multichannel outlets
// (output). Missing input channels are zero-padded; extra outlet channels
// (e.g. `chans` larger than the model output) are silenced.
void mcs_mab_tilde_perform64(t_mab_tilde* x, t_object* dsp64, double** ins, long numins, double** outs, long numouts, long sampleframes, long flags, void* userparam) {
    long n = sampleframes;
    if (n < 0) n = 0;

    // Bypass mode: pass through as many channels as available (flat order).
    if (!x->is_ready || x->is_bypass || !x->header) {
        long pass = (numins < numouts) ? numins : numouts;
        for (long ch = 0; ch < numouts; ch++) {
            double* out = outs[ch];
            double* in = (ch < pass && ins[ch]) ? ins[ch] : nullptr;
            for (long i = 0; i < n; i++) out[i] = in ? in[i] : 0.0;
        }
        return;
    }

    const long blk = (long)x->header->block_size;
    if (blk < 1) {
        for (long ch = 0; ch < numouts; ch++)
            for (long i = 0; i < n; i++) outs[ch][i] = 0.0;
        return;
    }

    // Model-declared channel counts (stable; never the per-inlet wiring).
    const long ci = x->channels_in;
    const long co = x->channels_out;
    const long n_batches = x->mcs_batches;
    if (n_batches < 1) {
        for (long ch = 0; ch < numouts; ch++)
            for (long i = 0; i < n; i++) outs[ch][i] = 0.0;
        return;
    }

    // Method-change detection (same as mab~/mc.mab~)
    if (!x->method_pending &&
        (x->header->method_id != x->active_method_id ||
         (long)x->header->channels_in != x->channels_in ||
         (long)x->header->channels_out != x->channels_out)) {
        x->method_pending = 1;
        qelem_set(x->io_qelem);
    }

    // Phase 6 (6.3): batch-major rows. Input row = b*ci + c, output row = b*co + c.
    const long total_ci = n_batches * ci;
    const long total_co = n_batches * co;
    const size_t input_buffer_stride = (size_t)total_ci * (size_t)blk;
    const size_t output_buffer_stride = (size_t)total_co * (size_t)blk;

    // A1: Double-buffered input. Max delivers the connected channels flat
    // (inlet 0 channels first, then inlet 1, ...), so the wiring below maps
    // flat index -> (batch, channel). Missing rows (unconnected channels) stay
    // nullptr and are zero-padded by block_accumulate_write.
    if (x->header->is_input_ready == 0) {
        uint32_t in_idx = x->header->input_buffer_index & 1;
        float* input_ptr = x->p_input + in_idx * input_buffer_stride;

        const double* wired[MAX_CHANNELS * MAX_CHANNELS] = { nullptr };
        long flat = 0;
        for (long b = 0; b < n_batches; b++) {
            long ch_conn = x->channel_map[b];
            if (ch_conn < 0) ch_conn = 0;
            if (ch_conn > ci) ch_conn = ci;
            for (long c = 0; c < ch_conn && flat < numins; c++, flat++) {
                if (ins[flat]) wired[b * ci + c] = ins[flat];
            }
        }

        if (block_accumulate_write(input_ptr, total_ci, blk, n,
                                   wired, total_ci, x->in_pos)) {
            x->header->input_buffer_index = 1 - in_idx;
            InterlockedExchange(&x->header->is_input_ready, 1);
            if (x->input_ready_event) {
                SetEvent(x->input_ready_event);
            }
        }
    }

    // A1: Double-buffered output. Drain the batch-major rows back into the
    // per-batch multichannel outlets (outlet b starts at flat b*per_outlet).
    if (x->header->is_output_ready == 1) {
        uint32_t out_idx = x->header->output_buffer_index & 1;
        float* output_ptr = x->p_output + out_idx * output_buffer_stride;

        // Per-outlet channel count as reported by mcs_multichanneloutputs.
        long per_outlet = (x->n_batches > 0) ? x->n_batches : co;
        if (per_outlet < 1) per_outlet = 1;

        double* wired_out[MAX_CHANNELS * MAX_CHANNELS] = { nullptr };
        for (long b = 0; b < n_batches; b++) {
            for (long c = 0; c < co; c++) {
                long flat_idx = b * per_outlet + c;
                if (flat_idx < numouts && outs[flat_idx]) {
                    wired_out[b * co + c] = outs[flat_idx];
                }
            }
        }

        if (block_accumulate_read(output_ptr, total_co, blk, n,
                                  wired_out, total_co, x->out_pos)) {
            InterlockedExchange(&x->header->is_output_ready, 0);
            x->header->output_buffer_index = 1 - out_idx;
        }

        // Outlets beyond the model's channel count per batch: silence
        // (no stale data), e.g. `chans 2` on a mono-output decode.
        for (long b = 0; b < n_batches; b++) {
            for (long c = co; c < per_outlet; c++) {
                long flat_idx = b * per_outlet + c;
                if (flat_idx < numouts && outs[flat_idx]) {
                    for (long i = 0; i < n; i++) outs[flat_idx][i] = 0.0;
                }
            }
        }
    } else {
        for (long ch = 0; ch < numouts; ch++) {
            double* out = outs[ch];
            for (long i = 0; i < n; i++) out[i] = 0.0;
        }
    }
}

// multichanneloutputs callback (mcs): called by Max per outlet index to
// determine how many channels that outlet produces. Returns the fixed count
// from `chans` (n_batches) if set, otherwise channels_out - same rule as
// mc.mab~, applied to every batch outlet.
long mcs_multichanneloutputs(t_mab_tilde* x, long index, long count) {
    (void)index; (void)count;
    if (x->n_batches > 0) {
        return x->n_batches;
    }
    return x->channels_out;
}

// inputchanged callback (mcs): called by Max when the channel count on a batch
// inlet changes. Updates channel_map[index] and publishes it to the worker.
// x->channels_in (model layout) is untouched; a mismatch with the model's
// per-batch input count is logged as a warning (nn_tilde-Parität P9).
long mcs_inputchanged(t_mab_tilde* x, long index, long count) {
    if (index < 0 || index >= MAX_CHANNELS) return 0;
    if (count < 1) count = 1;
    if (count > MAX_CHANNELS) count = MAX_CHANNELS;

    if (x->channel_map[index] != count) {
        x->channel_map[index] = count;
        if (x->header) {
            x->header->channel_map[index] = (uint32_t)count;
        }
        long total = 0;
        for (long i = 0; i < MAX_CHANNELS; i++) total += x->channel_map[i];
        post("mcs.mab~: batch inlet %ld channel count changed to %ld (total in=%ld)",
             index, count, total);
        if (count != x->channels_in) {
            post("mcs.mab~: warning: batch %ld has %ld channel(s), model expects "
                 "%ld per batch - unconnected channels are silenced",
                 index, count, x->channels_in);
        }
    }
    return 1;
}