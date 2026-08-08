# Implementation Plan & Checklist for mab_tilde Project

**Folder:** `doc/`  
**File:** `implementation_plan.md`

---

## 1. Overview
Create a crash‑safe, process‑isolated MaxMSP external (`mab~`, `mc.mab~`) and its Python backend (`inference_worker.py`) that replaces `nn_tilde`. The solution must:
- Use Windows shared memory and lock‑free SPSC ring buffer for audio block exchange.
- Support CPU/GPU inference, dynamic reload, runtime attribute setting, and model inspection (`dump`).
- Provide 1:1 message/attribute compatibility with `nn_tilde`.

---

## 2. First Debug Test Milestone

### Goal: First successful test in Max MSP
The external must be recognized by Max, load without errors, communicate with Python, and terminate cleanly.

### Success Criteria for First Test:
- [x] **External recognized by Max**: No errors when loading the package
- [x] **mab~ object loads**: `[mab~]` can be instantiated in a patch
- [ ] **Python server starts**: Background process launches successfully
- [ ] **Initial handshake**: C++ and Python exchange shared memory names
- [ ] **Shared memory mapped**: Both sides can read/write audio buffers
- [ ] **Python signals ready**: `is_python_ready` flag set to true
- [ ] **C++ detects ready**: `is_ready` flag becomes true
- [ ] **Clean shutdown**: Object deletion terminates Python process cleanly

### Test Procedure:
1. Build Debug: `cmake --build build --config Debug`
2. Copy `mab~.mxe64` to Max Packages folder
3. Open Max, create patch with `[mab~ test.ts forward 2048]`
4. Verify no errors in Max console
5. Turn DSP on, verify audio passes through
6. Delete object, verify clean shutdown

---

## 3. Critical Architecture Requirements

### 3.1 Asynchronous Background Initialization (Non-Blocking Startup)
- **Rule:** Never block the Max main thread during object creation (`new`) while Python boots and PyTorch loads the `.ts` model.
- **Implementation:**
  - Instantiation must immediately return.
  - Spawn the Python background process and perform model loading inside a **detached C++ background thread**.
  - The object starts in a safe **Bypass/Muted state**.
  - Once the background thread confirms the shared memory and backend are fully initialized, it atomically flips a flag to transition the object into active mode.

### 3.2 State Management: Bypass, `enable 0`, and DSP Toggling
- **Rule:** Never terminate or restart the Python process on `enable 0`, `bypass`, or when Max's global DSP is switched off. Restarting PyTorch takes seconds; state changes must be instantaneous.
- **Implementation:**
  - **`enable 0` / Bypass:** The C++ audio callback (`dsp64`) continues to run smoothly, but skips writing to the ring buffer, routing audio directly to the output (or silence). The Python process remains alive and waiting in a low-cpu poll state.
  - **DSP Off in Max:** Max stops calling `dsp64`. Python remains passively waiting. Data flow resumes instantly when DSP is turned back on.

### 3.3 Clean Shutdown & Destructor Logic
- **Rule:** Prevent zombie processes, dangling shared memory, and kernel leaks when the Max patch is closed or the object is deleted.
- **Implementation:**
  - In the C++ destructor (`~mab_tilde`):
    1. Send a clean shutdown signal/flag via the control ring buffer to Python.
    2. Wait briefly (max 500ms) for Python to exit gracefully.
    3. If it doesn't respond, forcefully terminate the background process using its process handle.
    4. Unmap Windows memory-mapped files and close all shared handles cleanly.

### 3.4 Crash Recovery & Monitoring
- **Rule:** If the Python worker crashes (e.g., due to a PyTorch OOM error), MaxMSP must survive completely unhindered.
- **Implementation:**
  - C++ must monitor the background process handle.
  - If the Python process dies unexpectedly, C++ instantly falls back to a safe **Bypass-Mode** and outputs a clear error message to the Max Console (e.g., `mab~: Python worker crashed. Check VRAM!`).
  - The user can fix the issue and use the `reload` command to restart the worker without restarting Max.

### 3.5 Real-Time Safety (No OS Locks in Audio Thread)
- **Rule:** Never use blocking OS synchronization primitives (e.g., `WaitForSingleObject`, mutexes) inside the Max audio callback (`dsp64`).
- **Implementation:** Synchronization must rely *exclusively* on lock-free SPSC ring buffers and atomic indices (`std::atomic`) with non-blocking poll mechanisms.

### 3.6 Shared Memory Handshake & Lifecycle
- **Rule:** Enforce a strict creation order to prevent race conditions.
- **Implementation:** Python boots, loads the `.ts` model, extracts required parameters (exact block size, channel count), creates the Windows Shared Memory (Memory-Mapped File) dynamically, and notifies C++ to attach. C++ must only attempt to map the memory *after* Python has initialized it.

### 3.7 Multi-Channel Memory Layout (`mc.mab~`)
- **Rule:** Standardize the raw data layout in shared memory for zero-copy efficiency.
- **Implementation:** Use a contiguous layout (e.g., shape `[num_channels, block_size]`) so Python can wrap it directly into a NumPy array and PyTorch tensor via `torch.from_numpy()` without expensive memory-copy overhead.

---

## 4. Detailed Checklist

### Phase 0 – Setup ✅ (COMPLETE)
- [x] Create `doc/` directory.
- [x] Add `WORKSPACE_AGENT_PROMPT.md` (already completed).
- [x] Verify workspace structure matches the provided hierarchy.
- [x] Create `requirements.txt` with minimal dependencies (`torch>=2.0.0`, `numpy>=1.20.0`).
- [x] Create `setup_env.bat` to bootstrap the virtual environment and install dependencies.
- [x] **Native Max SDK Build**: Migriert von min-devkit-Framework zu reinem nativen Max SDK (ext.h, z_dsp.h). Siehe `doc/toolchain.md`.
- [x] **Build-System**: Root `CMakeLists.txt` verwendet `add_library(mab_tilde MODULE ...)` mit direkten SDK-Include-Pfaden und `MaxAPI.lib`/`MaxAudio.lib` Import Libraries.
- [x] **Build verifiziert**: `mab~.mxe64` (55.296 Bytes) erfolgreich gebaut mit VS 2026 / MSVC 19.51.
- [x] **Crash-Fix**: `std::atomic<bool>` aus C-Struct entfernt → `long` Variablen verwendet (object_alloc() ruft keine C++ Konstruktoren auf).
- [x] **Entry-Point Fix**: `int main()` → `void ext_main()` (Max erwartet `ext_main` als Einstiegspunkt für .mxe64).
- [x] **extern "C"**: Alle Callbacks in `extern "C"` Block (Name Mangling verhindern).
- [x] **__declspec(dllexport)**: MSVC exportiert DLL-Symbole nicht automatisch.
- [x] **OUTPUT_NAME "mab~"**: Dateiname muss exakt dem Objektnamen entsprechen.
- [x] **IntelliSense-Konfiguration**: `.vscode/c_cpp_properties.json` mit Windows SDK und MSVC Pfaden.

### Phase 1 – Core C++ External (with Critical Architecture)

#### 1.1 Object Registration ✅ (COMPLETE)
- [x] Register `mab~` and `mc.mab~` classes with Max.
- [x] Set up new/free functions (`mab_tilde_new`, `mab_tilde_free`).
- [x] `ext_main` with `__declspec(dllexport)` and `extern "C"` for all callbacks.
- [x] `class_dspinit(c)`, `class_register(CLASS_BOX, c)`.
- [x] `OUTPUT_NAME "mab~"` in CMakeLists.txt.

#### 1.2 Asynchronous Initialization ⬜ (NOT STARTED)
- [ ] Add `#include <thread>` and `#include <atomic>` to mab_tilde.cpp
- [ ] Create `init_worker()` function to run in background thread
- [ ] Spawn detached `std::thread` in `mab_tilde_new()` that launches Python
- [ ] Use `long` (not `std::atomic<bool>`) for `is_ready` flag (C-Struct safety)
- [ ] Use `long` for `is_bypass` flag
- [ ] `mab_tilde_new()` returns immediately after spawning background thread
- [ ] Audio processing starts in bypass mode until `is_ready` becomes true
- [ ] Store Python process handle (`HANDLE`) in struct for clean termination
- [ ] Generate unique instance ID for shared memory naming

#### 1.3 Shared Memory Management (Handshake Protocol) ⬜ (NOT STARTED)
- [ ] Define `SharedMemoryHeader` struct in C++ (C-compatible, no C++ objects):
  - `uint32_t magic` (0x4D414254 = 'MABT')
  - `uint32_t version` (1)
  - `uint32_t block_size` (samples per block)
  - `uint32_t num_channels` (1 for mab~, up to 16 for mc.mab~)
  - `uint32_t input_offset` (byte offset to input buffer)
  - `uint32_t output_offset` (byte offset to output buffer)
  - `long is_input_ready` (atomic flag, set by Python)
  - `long is_output_ready` (atomic flag, set by Python)
  - `long is_python_ready` (atomic flag, set by Python)
- [ ] C++ polls for Python's ready signal via named event (`OpenEventW`)
- [ ] C++ maps existing shared memory using `OpenFileMappingW`
- [ ] C++ maps view using `MapViewOfFile`
- [ ] Validate shared memory header (magic number check)
- [ ] Store mapped pointers in struct for audio callback access
- [ ] Unmap and close handles in destructor

#### 1.4 Multi-Channel Memory Layout ⬜ (NOT STARTED)
- [ ] Implement contiguous layout: `[num_channels, block_size]`
- [ ] Calculate buffer sizes: `num_channels * block_size * sizeof(float)`
- [ ] Provide channel count parameter to Python via handshake
- [ ] Support dynamic channel count for `mc.mab~`

#### 1.5 Real-Time Safe Synchronization ⬜ (NOT STARTED)
- [ ] Replace blocking events with `long` atomic flags (volatile):
  - `is_input_ready` - set by Python when input block is ready
  - `is_output_ready` - set by Python when output block is processed
- [ ] Audio callback (`dsp64`) uses non-blocking poll:
  ```cpp
  if (x->is_input_ready) {
      // Copy input to shared memory
      x->is_input_ready = 0;
  }
  ```
- [ ] Bypass mode: when not ready, pass audio through unchanged
- [ ] No `WaitForSingleObject`, mutexes, or blocking calls in audio thread

#### 1.6 Process Lifecycle ⬜ (NOT STARTED)
- [ ] Parse Max arguments (`model.ts`, `method`, `buffer_size`, `channels`).
- [ ] Launch `python inference_worker.py` with appropriate args in background thread.
- [ ] Store process handle for clean termination.
- [ ] Implement graceful shutdown (`is_running` flag).
- [ ] Handle process startup failure gracefully (stay in bypass mode).

#### 1.7 Message Handlers ⬜ (NOT STARTED)
- [ ] `enable` - toggle bypass mode
- [ ] `gpu` - request GPU/CPU switch (async via ring buffer)
- [ ] `reload` - reload model (async via ring buffer)
- [ ] `dump` - request model info (async via ring buffer)
- [ ] `set` - set attribute (async via ring buffer)
- [ ] `get` - get attribute value (async via ring buffer)
- [ ] `method` - change inference method (async via ring buffer)
- [ ] `load` - change model dynamically (async via ring buffer)
- [ ] Forward generic `anything` messages to Python.

#### 1.8 Memory Cleanup ⬜ (NOT STARTED)
- [ ] Unmap shared memory, close handles, terminate Python process.
- [ ] Join background thread if still running.

### Phase 2 – Python Backend (with Critical Architecture)

#### 2.1 Argument Parsing ⬜ (PARTIALLY DONE)
- [x] Read command-line args: model path, method, buffer size, GPU flag
- [ ] Add shared memory name parameter (from C++)
- [ ] Add instance ID parameter (for unique naming)
- [ ] Add channel count parameter

#### 2.2 Shared Memory Creation (Handshake Protocol) ⬜ (PARTIALLY DONE)
- [x] Create shared memory segments using `CreateFileMappingW`
- [x] Write header with magic, block_size, num_channels, offsets
- [x] Signal C++ that shared memory is ready (via named event)
- [ ] Validate header structure matches C++ definition exactly
- [ ] Use `long` (c_bool) for atomic flags (not std::atomic)

#### 2.3 Multi-Channel Memory Layout ⬜ (NOT STARTED)
- [ ] Allocate contiguous buffer: `num_channels * block_size * 4` bytes
- [ ] Create NumPy view: `np.frombuffer(shared_mem, dtype=np.float32).reshape(num_channels, block_size)`
- [ ] Create PyTorch tensor: `torch.from_numpy(np_array)` (zero-copy)

#### 2.4 Ring Buffer (Control Messages) ⬜ (NOT STARTED)
- [ ] Implement `LockFreeRingBuffer` class to receive C++ messages.
- [ ] Parse incoming messages (`enable`, `gpu`, `reload`, `dump`, `set`, `get`, `method`, `load`).

#### 2.5 Model Management ⬜ (PARTIALLY DONE)
- [x] Load TorchScript model with `torch.jit.load`.
- [x] Move model to CPU or CUDA based on flag.
- [x] Support `reload` to re-load model on demand.
- [ ] Extract model's expected block size from input shape.

#### 2.6 Inference Loop ⬜ (PARTIALLY DONE)
- [x] Poll for input ready flag (non-blocking)
- [ ] Run `torch.no_grad()` inference on block.
- [ ] Write processed block back to output shared memory.
- [x] Set output ready flag.

#### 2.7 Runtime Attributes ⬜ (NOT STARTED)
- [ ] Store mutable attributes in a dict.
- [ ] Parse `set <name> <value>` messages.
- [ ] Parse `get <name>` messages and return values.

#### 2.8 Model Inspection (`dump`) ⬜ (NOT STARTED)
- [ ] Output model metadata (methods, shapes, attributes) to stdout.

#### 2.9 Graceful Exit ⬜ (NOT STARTED)
- [ ] Monitor global `running` flag to break loop and exit.
- [ ] Clean up shared memory handles.

---

## 5. Success Criteria
- **Functional**: All Max messages (`enable`, `gpu`, `reload`, `dump`, `set`, `get`, `method`, `load`, `print_available_models`, `download`, `delete`) work as specified.
- **Performance**: No audible dropouts; latency ≤ 5 ms; CPU usage < 15 % on a single core.
- **Stability**: Process terminates cleanly on object deletion; no memory leaks.
- **Compatibility**: Works on Windows 10/11 with Max 8+; supports both 32‑ and 64‑bit builds.
- **Real-Time Safety**: No blocking calls in audio thread; all synchronization lock-free.
- **Documentation**: All APIs are documented; a user can build and run the external with the provided instructions.

---

## 6. Technical Details

### 6.1 Shared Memory Header Structure (C++/Python)
```cpp
// C-compatible struct (no C++ objects, no std::atomic)
struct SharedMemoryHeader {
    uint32_t magic;           // 0x4D414254 ('MABT')
    uint32_t version;         // 1
    uint32_t block_size;      // samples per block
    uint32_t num_channels;    // 1 for mab~, up to 16 for mc.mab~
    uint32_t input_offset;    // bytes to input buffer
    uint32_t output_offset;   // bytes to output buffer
    long is_input_ready;      // atomic flag (volatile)
    long is_output_ready;     // atomic flag (volatile)
    long is_python_ready;     // atomic flag (volatile)
};
```

### 6.2 Audio Callback (dsp64) - Lock-Free Implementation
```cpp
void mab_tilde_perform64(t_mab_tilde* x, t_object* dsp64, double** ins, long numins, double** outs, long numouts, long sampleframes, long flags, void* userparam) {
    double* in = ins[0];
    double* out = outs[0];
    long n = sampleframes;

    if (!x->is_ready) {
        // Bypass mode: pass through
        for (long i = 0; i < n; i++) {
            out[i] = in[i];
        }
        return;
    }

    // Non-blocking audio processing via shared memory
    if (x->is_input_ready) {
        // Copy input to shared memory (float32)
        float* shm_in = (float*)x->p_input;
        for (long i = 0; i < n; i++) {
            shm_in[i] = (float)in[i];
        }
        x->is_input_ready = 0;
    }

    if (x->is_output_ready) {
        // Copy output from shared memory
        float* shm_out = (float*)x->p_output;
        for (long i = 0; i < n; i++) {
            out[i] = (double)shm_out[i];
        }
        x->is_output_ready = 0;
    }
}
```

### 6.3 Python Initialization Sequence
1. Parse command-line arguments (model path, method, buffer size, GPU flag, shm name, instance ID)
2. Load TorchScript model
3. Extract block size from model input shape
4. Create shared memory with header (CreateFileMappingW + MapViewOfFile)
5. Signal C++ that initialization is complete (SetEvent)
6. Enter inference loop (poll for input, process, write output)

### 6.4 C++ Background Thread Sequence
1. `mab_tilde_new()` spawns detached `std::thread`
2. Background thread:
   a. Generates unique instance ID
   b. Launches `python inference_worker.py <args> <shm_name> <instance_id>`
   c. Polls for named event (`OpenEventW` + `WaitForSingleObject` with timeout)
   d. Once signaled, opens shared memory (`OpenFileMappingW` + `MapViewOfFile`)
   e. Validates header (magic number check)
   f. Sets `is_ready = 1` (atomic)
3. Audio callback checks `is_ready` flag (non-blocking)

---

## 7. Comparison with nn_tilde

### Windows Performance Issues in nn_tilde
- **Memory Leak**: PyTorch threading issue on Windows (GitHub #24237)
- **Threading Disabled**: `m_use_thread = false` on Windows
- **Silence Output**: `fill_with_zero()` instead of bypass

### How mab_tilde Solves These
- **Separate Process**: Python runs in isolated process (no C++ threading)
- **Async Init**: Background thread doesn't block Max
- **Lock-Free IPC**: No OS synchronization in audio thread
- **Proper Bypass**: Audio passes through when not ready

---

## 8. Next Milestone: Phase 1.2/1.3 & Phase 2.1/2.2

### Goal: Asynchronous Background Initialization & Windows Shared Memory Handshake

### Phase 1.2 – Asynchronous Initialization (C++)
**Status:** ⬜ NOT STARTED

**Tasks:**
1. Add `#include <thread>` and `#include <atomic>` to mab_tilde.cpp
2. Create `init_worker(t_mab_tilde* x)` function:
   - Generate unique instance ID (e.g., from `GetCurrentProcessId()`)
   - Build Python command line with args
   - Launch Python process via `CreateProcessW`
   - Poll for ready event via `OpenEventW` + `WaitForSingleObject` (with timeout, NOT in audio thread)
   - Open shared memory via `OpenFileMappingW` + `MapViewOfFile`
   - Validate header (magic check)
   - Set `x->is_ready = 1`
3. In `mab_tilde_new()`: spawn `std::thread(init_worker, x).detach()`
4. In `mab_tilde_free()`: signal shutdown, terminate process, unmap memory

### Phase 1.3 – Shared Memory Management (C++)
**Status:** ⬜ NOT STARTED

**Tasks:**
1. Define `SharedMemoryHeader` struct (C-compatible, no C++ objects)
2. Implement `OpenFileMappingW` + `MapViewOfFile` in `init_worker()`
3. Validate header magic number
4. Store mapped pointers in struct
5. Implement cleanup in `mab_tilde_free()`

### Phase 2.1 – Argument Parsing (Python)
**Status:** ⬜ PARTIALLY DONE

**Tasks:**
1. Add `shm_name` argument to argparse
2. Add `instance_id` argument to argparse
3. Add `num_channels` argument to argparse
4. Add `block_size` argument to argparse (optional, defaults to 512)

### Phase 2.2 – Shared Memory Creation (Handshake Protocol)
**Status:** ⬜ PARTIALLY DONE

**Tasks:**
1. Verify `SharedMemoryHeader` struct matches C++ definition exactly (same field order, same types)
2. Ensure `is_input_ready`, `is_output_ready`, `is_python_ready` use `c_bool` (maps to `long` in C++)
3. Create named event (`CreateEventW`) for ready signal
4. Signal C++ via `SetEvent` after header initialization
5. Verify shared memory name format matches C++ (`MabSharedMem_{instance_id:08u}`)
6. Verify event name format matches C++ (`MabEvent_{instance_id:08u}`)

### Phase 2.3 – Inference Loop (Python)
**Status:** ⬜ PARTIALLY DONE

**Tasks:**
1. Implement proper polling loop with `time.sleep(0.001)` for low CPU
2. Check `is_input_ready` flag (non-blocking)
3. Run `torch.no_grad()` inference on input block
4. Write output to shared memory buffer
5. Set `is_output_ready` flag
6. Clear `is_input_ready` flag

---

## 9. Implementation Order (Recommended)

1. **Phase 1.2** (C++ Background Thread) - Spawn Python process, poll for ready event
2. **Phase 1.3** (C++ Shared Memory) - OpenFileMappingW, MapViewOfFile, validate header
3. **Phase 2.1** (Python Args) - Add shm_name, instance_id, num_channels arguments
4. **Phase 2.2** (Python Shared Memory) - Verify header struct matches, signal ready
5. **Phase 2.3** (Python Inference Loop) - Implement polling and pass-through
6. **Phase 1.5** (Audio Callback) - Update perform64 with shared memory I/O
7. **Phase 1.6** (Process Lifecycle) - Parse args, store handle, graceful shutdown
8. **Phase 1.8** (Memory Cleanup) - Unmap, close handles, terminate process
9. **Phase 1.7** (Message Handlers) - enable, gpu, reload, dump, set, get, method, load

---

*End of Implementation Plan & Checklist*
