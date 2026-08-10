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
// Version 2 adds method-aware metadata so C++ can rebuild inlets/outlets
// dynamically. Field order MUST match the Python SharedMemoryHeader exactly.
struct SharedMemoryHeader {
    uint32_t magic;           // 0x4D414254 ('MABT')
    uint32_t version;         // 2
    uint32_t block_size;      // samples per audio block (latent held at audio rate)
    uint32_t num_channels;    // legacy channel count (== channels_out)
    uint32_t channels_in;     // active method: input channels
    uint32_t channels_out;    // active method: output channels
    uint32_t latent_size;     // latent dimension of the active method
    uint32_t input_ratio;     // active method: input ratio
    uint32_t output_ratio;    // active method: output ratio
    char     method[64];      // active method name (forward/encode/decode/prior)
    uint32_t input_offset;    // bytes to input buffer
    uint32_t output_offset;   // bytes to output buffer
    uint32_t control_offset;  // bytes to control ring buffer
    long is_input_ready;      // atomic flag (volatile)
    long is_output_ready;     // atomic flag (volatile)
    long is_python_ready;     // atomic flag (volatile)
    long shutdown_flag;       // atomic flag (C++ tells Python to die)
};

// Compile-time check that both sides agree on the header size.
// 9x uint32 (36) + method[64] + 3x uint32 (12) + 4x long (16) = 128 bytes.
static_assert(sizeof(SharedMemoryHeader) == 128,
              "SharedMemoryHeader v2 must be 128 bytes (sync with Python)");

static t_class* mab_tilde_class = nullptr;

typedef struct _mab_tilde {
    t_pxobject ob;
    long is_ready;           // 1 = Python is connected & ready
    long is_bypass;          // 1 = bypass audio processing
    
    // Threading & Process
    std::thread* init_thread;
    HANDLE python_process;
    HANDLE ready_event;
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
    long cores;            // PyTorch-Inferenz-Threads (1 = kein All-Core-Spread)
    
    // Runtime state
    long num_channels;
    
    // Phase 3: method-aware IO layout (cached copy of the header's active method)
    char active_method[64];
    long channels_in;          // inlet count of the active method
    long channels_out;         // outlet count of the active method
    long in_pos;               // input accumulation position within one block
    long out_pos;              // output drain position within one block
    long method_pending;       // 1 = IO rebuild queued (qelem) but not applied
    
    // Control message buffer for anything forwarding
    char control_buffer[1024];
    long control_size;
    
    // Main-thread communication: qelem fires mab_tilde_apply_io on the Max
    // main thread (dsp_resize / outlet rebuild must never run on the audio
    // thread or the background init thread).
    t_qelem* io_qelem;
} t_mab_tilde;

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

    __declspec(dllexport) void ext_main(void* r);
}

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
    x->hMapFile = nullptr;
    x->header = nullptr;
    x->p_input = nullptr;
    x->p_output = nullptr;
    x->p_control = nullptr;

    x->model_path[0] = '\0';
    x->method_name[0] = '\0';
    x->buffer_size = 512;
    x->gpu = 0;
    x->cores = 1;
    x->control_size = 0;
    memset(x->control_buffer, 0, sizeof(x->control_buffer));

    // Phase 3: method-aware IO state (default 1-in/1-out until the worker
    // reports the real layout through the shared-memory header)
    x->active_method[0] = '\0';
    x->channels_in = 1;
    x->channels_out = 1;
    x->in_pos = 0;
    x->out_pos = 0;
    x->method_pending = 0;
    x->io_qelem = qelem_new(x, (method)mab_tilde_apply_io);

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
    if (argc >= 2 && !void_mode) {
        t_symbol* method_sym = atom_getsym(argv + 1);
        if (method_sym && method_sym->s_name) {
            strncpy(x->method_name, method_sym->s_name, sizeof(x->method_name) - 1);
        }
    }
    if (argc >= 3 && !void_mode) x->buffer_size = atom_getlong(argv + 2);
    if (argc >= 4 && !void_mode) x->gpu = atom_getlong(argv + 3);
    if (argc >= 5 && !void_mode) x->num_channels = atom_getlong(argv + 4);
    if (argc >= 6 && !void_mode) {
        x->cores = atom_getlong(argv + 5);
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

    // 5. Cleanup main-thread IO communication (must happen after the init
    //    thread has been joined so no pending qelem fires on a freed object)
    if (x->io_qelem) {
        qelem_unset(x->io_qelem);
        qelem_free(x->io_qelem);
        x->io_qelem = nullptr;
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

void mab_tilde_perform64(t_mab_tilde* x, t_object* dsp64, double** ins, long numins, double** outs, long numouts, long sampleframes, long flags, void* userparam) {
    long n = sampleframes;
    if (n < 0) n = 0;

    // Crash monitoring: check if Python process is still alive (non-blocking)
    if (x->is_ready && x->python_process) {
        DWORD exitCode = 0;
        if (GetExitCodeProcess(x->python_process, &exitCode)) {
            if (exitCode != STILL_ACTIVE) {
                // Python process has exited unexpectedly
                post("mab~: Python worker crashed. Check mab_worker.log for details (e.g. VRAM).");
                InterlockedExchange(&x->is_ready, 0);
                InterlockedExchange(&x->is_bypass, 1);
                x->in_pos = 0;
                x->out_pos = 0;
                // Clean up shared memory
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
                if (x->python_process) {
                    CloseHandle(x->python_process);
                    x->python_process = nullptr;
                }
                // Bypass mode: pass audio through (or silence for latent inlets)
                for (long ch = 0; ch < numouts; ch++) {
                    double* out = outs[ch];
                    double* in = (ch == 0 && numins > 0) ? ins[0] : nullptr;
                    for (long i = 0; i < n; i++) out[i] = in ? in[i] : 0.0;
                }
                return;
            }
        }
    }

    // Bypass mode: pass audio through unchanged when not ready
    if (!x->is_ready || x->is_bypass || !x->header) {
        for (long ch = 0; ch < numouts; ch++) {
            double* out = outs[ch];
            double* in = (ch == 0 && numins > 0) ? ins[0] : nullptr;
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
        (strcmp(x->header->method, x->active_method) != 0 ||
         (long)x->header->channels_in != x->channels_in ||
         (long)x->header->channels_out != x->channels_out)) {
        x->method_pending = 1;
        qelem_set(x->io_qelem);
    }

    // Write Input to Shared Memory, accumulating samples until one full block
    // (block_size) has been collected; only then is the block submitted to
    // Python. Latent channels are written at audio rate - Python reads the
    // last sample of each channel for decode/prior.
    if (x->header->is_input_ready == 0) {
        if (block_accumulate_write(x->p_input, channels_in, blk, n,
                                   ins, numins, x->in_pos)) {
            InterlockedExchange(&x->header->is_input_ready, 1);
        }
    }

    // Read Output from Shared Memory, draining the block_size-long result.
    if (x->header->is_output_ready == 1) {
        if (block_accumulate_read(x->p_output, channels_out, blk, n,
                                  outs, numouts, x->out_pos)) {
            InterlockedExchange(&x->header->is_output_ready, 0);
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
void mab_tilde_apply_io(t_mab_tilde* x) {
    if (!x->header) {
        x->method_pending = 0;
        return;
    }

    long new_in = (long)x->header->channels_in;
    long new_out = (long)x->header->channels_out;
    if (new_in < 1) new_in = 1;
    if (new_out < 1) new_out = 1;
    if (new_in > MAX_CHANNELS) new_in = MAX_CHANNELS;
    if (new_out > MAX_CHANNELS) new_out = MAX_CHANNELS;

    x->channels_in = new_in;
    x->channels_out = new_out;
    strncpy(x->active_method, x->header->method, sizeof(x->active_method) - 1);
    x->active_method[sizeof(x->active_method) - 1] = '\0';

    // Block-Geometrie hat sich geändert: Teilblöcke der alten Methode
    // verwerfen (verhindert versetzte Frames nach einem Methoden-/Modell-Wechsel).
    x->in_pos = 0;
    x->out_pos = 0;

    // Rebuild inlets (dsp_resize creates/frees the signal proxies)
    dsp_resize((t_pxobject*)x, new_in);

    // Rebuild signal outlets: free the existing chain, then recreate.
    while (x->ob.z_ob.o_outlet) {
        object_free((t_object*)x->ob.z_ob.o_outlet);
    }
    for (long i = 0; i < new_out; i++) {
        outlet_new((t_object*)x, "signal");
    }

    x->method_pending = 0;
    post("mab~: IO layout: %ld inlets, %ld outlets, method=%s",
         new_in, new_out, x->active_method);
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

    // --- Worker portabel starten (Pfad-Auflösung im Launch-Helper) ---
    char shm_name_utf8[256];
    WideCharToMultiByte(CP_UTF8, 0, shm_name, -1, shm_name_utf8,
                        (int)sizeof(shm_name_utf8), NULL, NULL);

    char argbuf[2048];
    snprintf(argbuf, sizeof(argbuf), "\"%s\" \"%s\" %ld %d \"%s\" %u %ld %ld",
             x->model_path, x->method_name, x->buffer_size,
             (int)x->gpu, shm_name_utf8, instance_id, x->num_channels,
             x->cores);

    WorkerProcess wp;
    worker_launch(argbuf, false, &wp);
    if (!wp.process) {
        post("mab~: Failed to launch Python process. Running in bypass.");
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
                    
                    InterlockedExchange(&x->is_bypass, 0); // Disable bypass
                    InterlockedExchange(&x->is_ready, 1);  // Mark as ready
                    // Phase 3: schedule the method-aware inlets/outlets on the
                    // Max main thread (dsp_resize/outlet_new must not run on
                    // this background thread). qelem_set is thread-safe.
                    x->in_pos = 0;
                    x->out_pos = 0;
                    x->method_pending = 1;
                    qelem_set(x->io_qelem);
                    post("mab~: Python worker ready, shared memory mapped successfully.");
                } else {
                    post("mab~ error: Invalid shared memory header magic.");
                    UnmapViewOfFile(pBuf);
                }
            } else {
                post("mab~ error: Failed to map shared memory view.");
            }
        } else {
            post("mab~ error: Failed to open shared memory mapping.");
        }
    } else {
        post("mab~ error: Timeout waiting for Python worker. Check mab_worker.log for details.");
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
    // Echter Setter (nn_tilde-Parität P3): der Worker lädt das Modell auf dem
    // neuen Device neu und re-applied die Attribute.
    char msg_buf[CONTROL_MSG_SIZE];
    snprintf(msg_buf, sizeof(msg_buf), "gpu %d", x->gpu);
    if (mab_enqueue_control(x, msg_buf)) {
        post("mab~: GPU mode set to %ld (worker reloading model)", flag);
    } else {
        post("mab~: GPU mode set to %ld (will apply on next load)", flag);
    }
}

void mab_tilde_reload(t_mab_tilde* x, t_symbol* s) {
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
    
    // 5. Reset method-aware layout state; the fresh worker handshake will
    //    trigger a rebuild via qelem with the new method's channels.
    x->active_method[0] = '\0';
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