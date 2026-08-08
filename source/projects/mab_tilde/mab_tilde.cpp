//=============================================================================
//  mab_tilde.cpp
//  Min-API external implementing mab~ and mc.mab~
//  CRITICAL ARCHITECTURE: Real-Time Safe IPC with Python Backend
//=============================================================================

#include "c74_min_api.h"
#include "c74_min_impl.h"
#include "c74_jitter.h"
#include "c74_msp.h"
#include "c74_ui.h"
#include "c74_ui_graphics.h"
#include "readerwriterqueue/readerwriterqueue.h"
#include "murmur/Murmur3.h"

#include <windows.h>
#include <process.h>
#include <string>
#include <vector>
#include <atomic>
#include <thread>
#include <chrono>
#include <cstdint>

// ---------------------------------------------------------------------------
//  Configuration & Constants
// ---------------------------------------------------------------------------

static constexpr const wchar_t* SHARED_MEMORY_NAME_PREFIX = L"MabSharedMem_";
static constexpr const wchar_t* EVENT_NAME_PREFIX        = L"MabEvent_";
static constexpr int      DEFAULT_BUFFER_SIZE          = 2048;           // samples
static constexpr int      MAX_MESSAGE_QUEUE_SIZE       = 1024;
static constexpr int      MAX_CHANNELS                 = 16;             // mc. convention
static constexpr uint32_t MAGIC_NUMBER                 = 0x4D414254;      // 'MABT'
static constexpr int      INIT_TIMEOUT_MS              = 10000;            // 10 seconds max wait

// ---------------------------------------------------------------------------
//  Shared Memory Header Structure (Handshake Protocol)
// ---------------------------------------------------------------------------

struct alignas(64) SharedMemoryHeader {
    uint32_t magic;                           // Validation signature (0x4D414254)
    uint32_t version;                         // Header version
    uint32_t block_size;                      // Samples per block
    uint32_t num_channels;                    // Number of channels (1 for mab~, up to 16 for mc.mab~)
    uint32_t input_offset;                    // Byte offset to input buffer
    uint32_t output_offset;                   // Byte offset to output buffer
    std::atomic<bool> is_input_ready;         // Set by Python when input block is ready
    std::atomic<bool> is_output_ready;        // Set by Python when output block is processed
    std::atomic<bool> is_python_ready;        // Set by Python when initialization complete
    char       padding[32];                   // Padding for alignment
};

// ---------------------------------------------------------------------------
//  Shared State (audio block + control)
// ---------------------------------------------------------------------------

struct SharedState {
    // Shared memory handles
    HANDLE hMapInput  = nullptr;
    HANDLE hMapOutput = nullptr;
    void*  pInput     = nullptr;
    void*  pOutput    = nullptr;
    
    // Shared memory header (mapped from Python-created segment)
    SharedMemoryHeader* pHeader = nullptr;
    
    // Named objects for handshake
    std::wstring shared_mem_name;
    std::wstring ready_event_name;
    
    // Process handling
    PROCESS_INFORMATION pi{};
    std::wstring   python_exe;
    std::wstring   script_path;
    int            buffer_size;
    int            num_channels;
    std::wstring   model_path;
    std::wstring   method_name;
    bool           use_gpu;
    
    // Real-time safe state flags
    std::atomic<bool> is_running{true};
    std::atomic<bool> is_ready{false};         // Set when Python signals ready
    std::atomic<bool> is_bypass{true};          // Start in bypass mode
    
    // Lock-free SPSC queue for control messages (C++ → Python)
    moodycamel::ConcurrentQueue<t_max_symbol*> ctrl_queue;
    
    // Background thread handle
    std::thread*   init_thread = nullptr;
};

static SharedState* g_shared = nullptr; // singleton per object instance

// ---------------------------------------------------------------------------
//  Utility Functions (Windows)
// ---------------------------------------------------------------------------

static std::wstring wformat(const wchar_t* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    wchar_t buffer[256];
    vswprintf_s(buffer, fmt, args);
    va_end(args);
    return buffer;
}

// Generate unique names for shared memory and events
static std::wstring generate_unique_name(const wchar_t* prefix, uint32_t instance_id) {
    return wformat(L"%s%08u", prefix, instance_id);
}

// Open existing shared memory created by Python (handshake protocol)
static bool open_shared_memory(const std::wstring& name, HANDLE* h_map, void** data_out, size_t size) {
    HANDLE h_file = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, name.c_str());
    if (!h_file) return false;
    
    void* data = MapViewOfFile(h_file, FILE_MAP_ALL_ACCESS, 0, 0, size);
    if (!data) {
        CloseHandle(h_file);
        return false;
    }
    
    *h_map = h_file;
    *data_out = data;
    return true;
}

// Open existing named event
static HANDLE open_event(const std::wstring& name) {
    return OpenEventW(SYNCHRONIZE | EVENT_MODIFY_STATE, FALSE, name.c_str());
}

// ---------------------------------------------------------------------------
//  Background Initialization Thread (Async Init)
// ---------------------------------------------------------------------------

// Background worker function - runs in detached thread
static void init_worker(void* userdata) {
    SharedState* state = static_cast<SharedState*>(userdata);
    
    // Build command line: python inference_worker.py <model> <method> <bufsize> <gpu> <shm_name> <instance_id>
    std::wstring cmd = L"python \"" + state->script_path + L"\" \"" + 
                       state->model_path + L"\" \"" + state->method_name + L"\" " + 
                       std::to_wstring(state->buffer_size) + 
                       L" " + (state->use_gpu ? L"1" : L"0") +
                       L" \"" + state->shared_mem_name + L"\" " +
                       std::to_wstring(GetCurrentProcessId());
    
    // Launch Python process
    STARTUPINFOW si{};
    PROCESS_INFORMATION pi{};
    si.cb = sizeof(si);
    
    if (!CreateProcessW(
            nullptr,
            &cmd[0],
            nullptr,
            nullptr,
            FALSE,
            0,
            nullptr,
            nullptr,
            &si,
            &pi)) {
        min_err("Failed to launch inference_worker.py");
        return;
    }
    
    state->pi = pi;
    
    // Wait for Python to initialize and create shared memory
    // Poll for the ready event with timeout
    HANDLE hReady = open_event(state->ready_event_name);
    if (!hReady) {
        min_err("Failed to open ready event");
        TerminateProcess(pi.hProcess, 0);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        return;
    }
    
    // Wait for Python to signal ready (with timeout)
    DWORD result = WaitForSingleObject(hReady, INIT_TIMEOUT_MS);
    CloseHandle(hReady);
    
    if (result != WAIT_OBJECT_0) {
        min_err("Python initialization timeout");
        TerminateProcess(pi.hProcess, 0);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        return;
    }
    
    // Calculate total buffer size: header + input + output
    size_t total_size = sizeof(SharedMemoryHeader) + 
                        state->buffer_size * state->num_channels * sizeof(float) +
                        state->buffer_size * state->num_channels * sizeof(float);
    
    // Open the shared memory created by Python
    HANDLE hMap = nullptr;
    void* pData = nullptr;
    if (!open_shared_memory(state->shared_mem_name, &hMap, &pData, total_size)) {
        min_err("Failed to open shared memory from Python");
        TerminateProcess(pi.hProcess, 0);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        return;
    }
    
    // Map header and buffers
    state->hMapInput = hMap;
    state->pHeader = static_cast<SharedMemoryHeader*>(pData);
    state->pInput = static_cast<char*>(pData) + state->pHeader->input_offset;
    state->pOutput = static_cast<char*>(pData) + state->pHeader->output_offset;
    
    // Verify magic number
    if (state->pHeader->magic != MAGIC_NUMBER) {
        min_err("Invalid shared memory header");
        UnmapViewOfFile(pData);
        CloseHandle(hMap);
        TerminateProcess(pi.hProcess, 0);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        return;
    }
    
    // Verify block size matches
    if (state->pHeader->block_size != static_cast<uint32_t>(state->buffer_size)) {
        min_err("Block size mismatch with Python");
        UnmapViewOfFile(pData);
        CloseHandle(hMap);
        TerminateProcess(pi.hProcess, 0);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        return;
    }
    
    // Signal that we're ready
    state->is_ready.store(true, std::memory_order_release);
    state->is_bypass.store(false, std::memory_order_release);
}

// ---------------------------------------------------------------------------
//  Process Management
// ---------------------------------------------------------------------------

static void terminate_python_process(SharedState* state) {
    if (state->pi.hProcess) {
        TerminateProcess(state->pi.hProcess, 0);
        CloseHandle(state->pi.hProcess);
        CloseHandle(state->pi.hThread);
        ZeroMemory(&state->pi, sizeof(state->pi));
    }
}

// ---------------------------------------------------------------------------
//  Message Handling
// ---------------------------------------------------------------------------

// Forward declaration of helper to send a Max symbol to Python via the lock-free queue
static void enqueue_ctrl_message(SharedState* state, t_max_symbol* msg);

// ---------------------------------------------------------------------------
//  Object Lifecycle (new / free)
// ---------------------------------------------------------------------------

static t_max_err mab_tilde_new(t_max_symbol* s, long argc, t_atom* argv) {
    // Allocate state
    SharedState* state = new SharedState();
    g_shared = state;
    
    // Parse arguments: [model.ts (method) (buffer_size) (channels)]
    std::wstring model_w;
    std::wstring method_w = L"forward";
    int buffer_size = DEFAULT_BUFFER_SIZE;
    int num_channels = 1;  // Default to mono for mab~
    
    if (argc > 0) {
        model_w = std::wstring(argv[0].a_wchar);
    }
    if (argc > 1) {
        method_w = std::wstring(argv[1].a_wchar);
    }
    if (argc > 2) {
        buffer_size = atom_getint(argv[2]);
    }
    if (argc > 3) {
        num_channels = atom_getint(argv[3]);
    }
    
    // Convert to UTF-8 for easier handling
    std::string model_utf8 = std::string(model_w.begin(), model_w.end());
    std::string method_utf8 = std::string(method_w.begin(), method_w.end());
    
    // Store in state (for later use in messages)
    state->model_path = model_w;
    state->method_name = method_w;
    state->buffer_size = buffer_size;
    state->num_channels = num_channels;
    state->use_gpu = false;  // Default to CPU
    
    // Generate unique names for this instance
    static uint32_t instance_counter = 0;
    uint32_t instance_id = ++instance_counter;
    state->shared_mem_name = generate_unique_name(SHARED_MEMORY_NAME_PREFIX, instance_id);
    state->ready_event_name = generate_unique_name(EVENT_NAME_PREFIX, instance_id);
    
    // Store script path (assumed to be in same folder as external)
    state->script_path = L"inference_worker.py";
    
    // Launch Python process in background thread (ASYNC INIT)
    // This does NOT block the Max main thread
    state->init_thread = new std::thread(init_worker, state);
    
    // Return immediately - audio will be in bypass mode until ready
    return 0;
}

static t_max_err mab_tilde_free(void* data) {
    SharedState* state = static_cast<SharedState*>(data);
    if (!state) return 0;
    
    // Signal Python to exit
    state->is_running.store(false, std::memory_order_release);
    
    // Wait for background thread to finish (with timeout)
    if (state->init_thread && state->init_thread->joinable()) {
        state->init_thread->join();
        delete state->init_thread;
        state->init_thread = nullptr;
    }
    
    // Clean up shared memory
    if (state->pHeader) {
        UnmapViewOfFile(state->pHeader);
    }
    if (state->hMapInput) {
        CloseHandle(state->hMapInput);
    }
    
    // Close process handle
    terminate_python_process(state);
    
    delete state;
    g_shared = nullptr;
    return 0;
}

// ---------------------------------------------------------------------------
//  Audio Processing (dsp64) - REAL-TIME SAFE
// ---------------------------------------------------------------------------

static void mab_dsp64(t_object* x, long nframes, t_symbol* s, void* stack[]) {
    SharedState* state = static_cast<SharedState*>(x);
    if (!state) return;
    
    // Check if Python is ready (non-blocking)
    if (!state->is_ready.load(std::memory_order_acquire)) {
        // Bypass mode: pass through audio unchanged
        for (int ch = 0; ch < state->num_channels; ++ch) {
            float* input = static_cast<float*>(stack[ch]);
            float* output = static_cast<float*>(stack[ch + state->num_channels]);
            for (long i = 0; i < nframes; ++i) {
                output[i] = input[i];
            }
        }
        return;
    }
    
    // Real-time safe processing - NO BLOCKING CALLS
    // Use lock-free atomic operations only
    
    // Copy input to shared memory (if ready)
    if (state->pHeader && state->pHeader->is_input_ready.load(std::memory_order_acquire)) {
        for (int ch = 0; ch < state->num_channels; ++ch) {
            float* input = static_cast<float*>(stack[ch]);
            float* pChInput = static_cast<float*>(state->pInput) + ch * state->buffer_size;
            for (long i = 0; i < nframes; ++i) {
                pChInput[i] = input[i];
            }
            // Signal that input is ready
            state->pHeader->is_input_ready.store(false, std::memory_order_release);
        }
    }
    
    // Copy output from shared memory (if ready)
    if (state->pHeader && state->pHeader->is_output_ready.load(std::memory_order_acquire)) {
        for (int ch = 0; ch < state->num_channels; ++ch) {
            float* output = static_cast<float*>(stack[ch + state->num_channels]);
            float* pChOutput = static_cast<float*>(state->pOutput) + ch * state->buffer_size;
            for (long i = 0; i < nframes; ++i) {
                output[i] = pChOutput[i];
            }
            // Signal that output is consumed
            state->pHeader->is_output_ready.store(false, std::memory_order_release);
        }
    }
}

// ---------------------------------------------------------------------------
//  Max Message Handlers
// ---------------------------------------------------------------------------

static t_max_err handle_enable(t_max_symbol* msg, t_atom* argv, int argc, void* userdata) {
    SharedState* state = static_cast<SharedState*>(userdata);
    if (argc == 1) {
        bool enable = atom_getint(argv) != 0;
        state->is_bypass.store(!enable, std::memory_order_release);
        // Also send to Python via control queue
        enqueue_ctrl_message(state, msg);
    }
    return 0;
}

static t_max_err handle_gpu(t_max_symbol* msg, t_atom* argv, int argc, void* userdata) {
    SharedState* state = static_cast<SharedState*>(userdata);
    if (argc == 1) {
        bool use_gpu = atom_getint(argv) != 0;
        state->use_gpu = use_gpu;
        // Send to Python via control queue
        enqueue_ctrl_message(state, msg);
    }
    return 0;
}

static t_max_err handle_reload(t_max_symbol* msg, t_atom* argv, int argc, void* userdata) {
    SharedState* state = static_cast<SharedState*>(userdata);
    enqueue_ctrl_message(state, msg);
    return 0;
}

static t_max_err handle_dump(t_max_symbol* msg, t_atom* argv, int argc, void* userdata) {
    SharedState* state = static_cast<SharedState*>(userdata);
    enqueue_ctrl_message(state, msg);
    return 0;
}

static t_max_err handle_set(t_max_symbol* msg, t_atom* argv, int argc, void* userdata) {
    SharedState* state = static_cast<SharedState*>(userdata);
    // Forward the entire message to Python
    enqueue_ctrl_message(state, msg);
    return 0;
}

// Generic handler for any Max message (including dump, set, reload)
static t_max_err anything(t_max_symbol* msg, t_atom* argv, int argc, t_atom* att, void* userdata) {
    SharedState* state = static_cast<SharedState*>(userdata);
    // Forward the message symbol to Python for processing
    enqueue_ctrl_message(state, msg);
    return 0;
}

// Enqueue a control message to the Python process
static void enqueue_ctrl_message(SharedState* state, t_max_symbol* msg) {
    // The queue is lock-free; just push the symbol (copy it)
    state->ctrl_queue.enqueue(msg);
}

// ---------------------------------------------------------------------------
//  Object Life-cycle Registration
// ---------------------------------------------------------------------------

extern "C" {
    // Max calls this entry point when the external is loaded
    t_max_err ext_main(void* r, void* l, t_symbol* s, t_symbol* ps, int argc, t_atom* argv) {
        // Register the class descriptors
        t_symbol* sym_mab = gensym("mab~");
        t_symbol* sym_mc  = gensym("mc.mab~");
        
        // Create class structs
        static t_class* c_mab = nullptr;
        static t_class* c_mc  = nullptr;
        
        // mab~ class
        c_mab = max_class_new(sym_mab, "mab~", sizeof(SharedState), nullptr, nullptr, 0);
        max_class_addmethod(c_mab, (t_method)handle_enable, "enable", A_DEFLONG, 0);
        max_class_addmethod(c_mab, (t_method)handle_gpu, "gpu", A_DEFLONG, 0);
        max_class_addmethod(c_mab, (t_method)handle_reload, "reload", A_DEFSYM, 0);
        max_class_addmethod(c_mab, (t_method)handle_dump, "dump", A_DEFSYM, 0);
        max_class_addmethod(c_mab, (t_method)handle_set, "set", A_GIMME, 0);
        max_class_addmethod(c_mab, (t_method)anything, "anything", A_GIMME, 0);
        max_class_addmethod(c_mab, (t_method)mab_dsp64, "dsp64", A_GIMME, 0);
        max_class_set_assist(c_mab, nullptr);
        max_class_set_freefun(c_mab, mab_tilde_free);
        max_class_set_newfun(c_mab, mab_tilde_new);
        
        // mc.mab~ class (multi-channel variant)
        c_mc = max_class_new(sym_mc, "mc.mab~", sizeof(SharedState), nullptr, nullptr, 0);
        max_class_addmethod(c_mc, (t_method)handle_enable, "enable", A_DEFLONG, 0);
        max_class_addmethod(c_mc, (t_method)handle_gpu, "gpu", A_DEFLONG, 0);
        max_class_addmethod(c_mc, (t_method)handle_reload, "reload", A_DEFSYM, 0);
        max_class_addmethod(c_mc, (t_method)handle_dump, "dump", A_DEFSYM, 0);
        max_class_addmethod(c_mc, (t_method)handle_set, "set", A_GIMME, 0);
        max_class_addmethod(c_mc, (t_method)anything, "anything", A_GIMME, 0);
        max_class_addmethod(c_mc, (t_method)mab_dsp64, "dsp64", A_GIMME, 0);
        max_class_set_assist(c_mc, nullptr);
        max_class_set_freefun(c_mc, mab_tilde_free);
        max_class_set_newfun(c_mc, mab_tilde_new);
        
        // Return success
        return 0;
    }
}