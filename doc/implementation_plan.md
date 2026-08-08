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
- [ ] **External recognized by Max**: No errors when loading the package
- [ ] **mab~ object loads**: `[mab~]` can be instantiated in a patch
- [ ] **Python server starts**: Background process launches successfully
- [ ] **Initial handshake**: C++ and Python exchange shared memory names
- [ ] **Shared memory mapped**: Both sides can read/write audio buffers
- [ ] **Python signals ready**: `is_python_ready` flag set to true
- [ ] **C++ detects ready**: `is_ready` flag becomes true
- [ ] **Clean shutdown**: Object deletion terminates Python process cleanly

### Test Procedure:
1. Build Debug: `cmake --build build --config Debug`
2. Copy `mab_tilde.mxf` to Max Packages folder
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

### Phase 0 – Setup
- [x] Create `doc/` directory.
- [x] Add `WORKSPACE_AGENT_PROMPT.md` (already completed).
- [x] Verify workspace structure matches the provided hierarchy.
- [x] Create `requirements.txt` with minimal dependencies (`torch>=2.0.0`, `numpy>=1.20.0`).
- [x] Create `setup_env.bat` to bootstrap the virtual environment and install dependencies.
- [x] Update `mab_tilde.cpp` for smart Python path resolution (detect `.venv` or `env` in package folder).
- [x] **Native Max SDK Build**: Migriert von min-devkit-Framework zu reinem nativen Max SDK (ext.h, z_dsp.h). Siehe `doc/toolchain.md`.
- [x] **Build-System**: Root `CMakeLists.txt` verwendet `add_library(mab_tilde MODULE ...)` mit direkten SDK-Include-Pfaden und `MaxAPI.lib`/`MaxAudio.lib` Import Libraries.
- [x] **Build verifiziert**: `mab_tilde.mxe64` (55.296 Bytes) erfolgreich gebaut mit VS 2026 / MSVC 19.51.

### Phase 1 – Core C++ External (with Critical Architecture)

#### 1.1 Object Registration
- [x] Register `mab~` and `mc.mab~` classes with Max.
- [x] Set up new/free functions (`mab_tilde_new`, `mab_tilde_free`).

#### 1.2 Asynchronous Initialization
- [x] Create background thread for Python process launch (detached from Max main thread)
- [x] Implement `init_worker()` function to run in background thread
- [x] Add `std::atomic<bool> is_ready` flag for initialization state
- [x] Add `std::atomic<bool> is_bypass` flag for safe bypass mode
- [x] `mab_tilde_new()` returns immediately after spawning background thread
- [x] Audio processing starts in bypass mode until `is_ready` becomes true

#### 1.3 Shared Memory Management (Handshake Protocol)
- [x] **Python creates** shared memory segments (C++ only opens)
- [x] Create shared memory header structure with:
  - `uint32_t magic` (validation signature)
  - `uint32_t block_size` (samples per block)
  - `uint32_t num_channels` (1 for mab~, up to 16 for mc.mab~)
  - `uint32_t input_offset` (byte offset to input buffer)
  - `uint32_t output_offset` (byte offset to output buffer)
- [x] C++ polls for Python's ready signal via named event or atomic flag
- [x] C++ maps existing shared memory using `OpenFileMappingW`
- [x] Validate shared memory header before use

#### 1.4 Multi-Channel Memory Layout
- [x] Implement contiguous layout: `[num_channels, block_size]`
- [x] Calculate buffer sizes: `num_channels * block_size * sizeof(float)`
- [x] Provide channel count parameter to Python via handshake
- [x] Support dynamic channel count for `mc.mab~`

#### 1.5 Real-Time Safe Synchronization
- [x] Replace blocking events with `std::atomic<bool>` flags:
  - `is_input_ready` - set by Python when input block is ready
  - `is_output_ready` - set by Python when output block is processed
- [x] Implement lock-free SPSC ring buffer for control messages (already using `moodycamel::ConcurrentQueue`)
- [x] Audio callback (`dsp64`) uses non-blocking poll:
  ```cpp
  if (is_input_ready.load(std::memory_order_acquire)) {
      // Copy input to processing buffer
      is_input_ready.store(false, std::memory_order_release);
  }
  ```
- [x] Bypass mode: when not ready, pass audio through unchanged

#### 1.6 Process Lifecycle
- [x] Parse Max arguments (`model.ts`, `method`, `buffer_size`, `channels`).
- [x] Launch `python inference_worker.py` with appropriate args in background thread.
- [x] Store process handle for clean termination.
- [x] Implement graceful shutdown (`is_running` flag).
- [x] Handle process startup failure gracefully (stay in bypass mode).

#### 1.7 Message Handlers
- [x] `enable` - toggle bypass mode
- [x] `gpu` - request GPU/CPU switch (async via ring buffer)
- [x] `reload` - reload model (async via ring buffer)
- [x] `dump` - request model info (async via ring buffer)
- [x] `set` - set attribute (async via ring buffer)
- [x] `get` - get attribute value (async via ring buffer)
- [x] `method` - change inference method (async via ring buffer)
- [x] `load` - change model dynamically (async via ring buffer)
- [x] Forward generic `anything` messages to Python.

#### 1.8 Memory Cleanup
- [x] Unmap shared memory, close handles, terminate Python process.
- [x] Join background thread if still running.

### Phase 2 – Python Backend (with Critical Architecture)

#### 2.1 Argument Parsing
- [x] Read command-line args: model path, method, buffer size, GPU flag, channel count, shared memory name.

#### 2.2 Shared Memory Creation (Handshake Protocol)
- [x] Create shared memory segments using `CreateFileMappingW`
- [x] Write header with magic, block_size, num_channels, offsets
- [x] Signal C++ that shared memory is ready (via named event or atomic flag)
- [x] Open existing shared memory for reading/writing

#### 2.3 Multi-Channel Memory Layout
- [x] Allocate contiguous buffer: `num_channels * block_size * 4` bytes
- [x] Create NumPy view: `np.frombuffer(shared_mem, dtype=np.float32).reshape(num_channels, block_size)`
- [x] Create PyTorch tensor: `torch.from_numpy(np_array)` (zero-copy)

#### 2.4 Ring Buffer (Control Messages)
- [x] Implement `LockFreeRingBuffer` class to receive C++ messages.
- [x] Parse incoming messages (`enable`, `gpu`, `reload`, `dump`, `set`, `get`, `method`, `load`).

#### 2.5 Model Management
- [x] Load TorchScript model with `torch.jit.load`.
- [x] Move model to CPU or CUDA based on flag.
- [x] Support `reload` to re-load model on demand.
- [x] Extract model's expected block size from input shape.

#### 2.6 Inference Loop
- [x] Poll for input ready flag (non-blocking)
- [x] Run `torch.no_grad()` inference on block.
- [x] Write processed block back to output shared memory.
- [x] Set output ready flag.

#### 2.7 Runtime Attributes
- [x] Store mutable attributes in a dict.
- [x] Parse `set <name> <value>` messages.
- [x] Parse `get <name>` messages and return values.

#### 2.8 Model Inspection (`dump`)
- [x] Output model metadata (methods, shapes, attributes) to stdout.

#### 2.9 Graceful Exit
- [x] Monitor global `running` flag to break loop and exit.

---

## 5. Success Criteria
- **Functional**: All Max messages (`enable`, `gpu`, `reload`, `dump`, `set`, `get`, `method`, `load`, `print_available_models`, `download`, `delete`) work as specified.
- **Performance**: No audible dropouts; latency ≤ 5 ms; CPU usage < 15 % on a single core.
- **Stability**: Process terminates cleanly on object deletion; no memory leaks.
- **Compatibility**: Works on Windows 10/11 with Max 8+; supports both 32‑ and 64‑bit builds.
- **Real-Time Safety**: No blocking calls in audio thread; all synchronization lock-free.
- **Documentation**: All APIs are documented; a user can build and run the external with the provided instructions.

---

## 6. Technical Details

### 6.1 Shared Memory Header Structure (C++/Python)
```cpp
struct SharedMemoryHeader {
    uint32_t magic;           // 0x4D414254 ('MABT')
    uint32_t version;         // 1
    uint32_t block_size;      // samples per block
    uint32_t num_channels;    // 1 for mab~, up to 16 for mc.mab~
    uint32_t input_offset;    // bytes to input buffer
    uint32_t output_offset;   // bytes to output buffer
    std::atomic<bool> is_input_ready;
    std::atomic<bool> is_output_ready;
    std::atomic<bool> is_python_ready;
};
```

### 6.2 Audio Callback (dsp64) - Lock-Free Implementation
```cpp
void mab_dsp64(t_object* x, long nframes, t_symbol* s, void* stack[]) {
    if (!state->is_ready.load(std::memory_order_acquire)) {
        // Bypass mode: pass through
        for (int ch = 0; ch < state->num_channels; ++ch) {
            float* input = (float*)stack[ch];
            float* output = (float*)stack[ch + 1];
            memcpy(output, input, nframes * sizeof(float));
        }
        return;
    }
    
    // Non-blocking audio processing
    if (state->is_input_ready.load(std::memory_order_acquire)) {
        // Copy input to shared memory
        memcpy(state->pInput, input_buffer, nframes * sizeof(float));
        state->is_input_ready.store(false, std::memory_order_release);
    }
    
    if (state->is_output_ready.load(std::memory_order_acquire)) {
        // Copy output from shared memory
        memcpy(output_buffer, state->pOutput, nframes * sizeof(float));
        state->is_output_ready.store(false, std::memory_order_release);
    }
}
```

### 6.3 Python Initialization Sequence
1. Parse command-line arguments
2. Load TorchScript model
3. Extract block size from model input shape
4. Create shared memory with header
5. Signal C++ that initialization is complete
6. Enter inference loop

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

*End of Implementation Plan & Checklist*