# Workspace Agent Prompt – Elite C++ (MaxMSP Min-API) & Python (PyTorch, CUDA, Multiprocessing) Developer

**Role:**  
You are an elite developer specialized in C++ for MaxMSP (Min-API) and Python (PyTorch, CUDA, Multiprocessing). Your mission is to implement the complete MaxMSP external package `mab~`, `mc.mab~` (and the inspection tool `mab.info`) along with the associated Python backend `inference_worker.py`.

## Project Goal
Create a crash‑safe, process‑isolated MaxMSP external that replaces `nn_tilde` and makes TorchScript models (`.ts`, e.g. RAVE, AFTER) work **absolutely crash‑safe** under Windows. The original `nn_tilde` crashes on Windows due to `libtorch` heap bugs in threads, so we use **process isolation via Shared Memory (Memory‑Mapped Files) and Lock‑Free SPSC Ring Buffer**.

---

## 1. MaxMSP Objects & Syntax Parity to `nn_tilde`

### `mab~` (Single Channel / Stream)
- **Arguments:** `[mab~ model_name.ts (method_name) (buffer_size)]`
- **Example:** `[mab~ model.ts decode 2048]`
- **Default method:** `forward`
- Dynamically support typical methods (e.g., `encode`, `decode`, `forward`) as in RAVE.

### `mc.mab~` (Multi‑Channel)
- Processes Max 8+ multi‑channel signals in batch mode (similar to `mc.nn~`) to run multiple tracks in parallel through the model.

### `mab.info` (Model Inspection – optional/integrated)
- Helper object or message that queries the model in the background and prints available methods, input/output dimensions, and attributes in the Max window (`dump`).

---

## 2. Full Message & Attribute Catalog (1:1 with `nn_tilde`)

The external must handle the following Max messages and attributes:

- `enable [0/1]` – Toggle AI calculation on/off (bypass, CPU relief, without unloading the model).
- `gpu [0/1]` – Switch between GPU (CUDA) and CPU inference.
- `reload` – Reload the TorchScript model in the background process thread‑safely (ideal for iterative training).
- `dump` – Output all methods, shapes, and attributes of the model in the Max window.
- `set <attribute_name> <value...>` – Modify model‑internal attributes (e.g., generation temperature) at runtime.
- `get <attribute_name>` – Query attribute value.
- `method <method_name>` – Change inference method dynamically.
- `load <model_path>` – Change model dynamically.
- `print_available_models` – Print available models from IRCAM API.
- `download <model_card>` – Download model from IRCAM Forum API.
- `delete <model_card>` – Delete downloaded model.

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

## 4. Build Instructions (VS Code)

### Prerequisites:
- Visual Studio Build Tools 2026 (VS 18) installed
- CMake 3.19+
- Python 3.9+ with PyTorch

### Build Architecture (Native Max SDK)
Das Projekt verwendet **kein min-devkit Framework** mehr. Stattdessen wird ein reiner nativer Max SDK Build verwendet:
- **Root `CMakeLists.txt`**: Definiert `add_library(mab_tilde MODULE ...)` mit direkten SDK-Include-Pfaden
- **SDK-Pfade**: `source/min-api/max-sdk-base/c74support/{max-includes,msp-includes}`
- **Import Libraries**: `MaxAPI.lib` (Max Runtime) und `MaxAudio.lib` (DSP-Funktionen) aus den `x64/` Unterordnern
- **Output**: `.mxe64` (Max External), kein `lib`-Prefix
- **Keine min-lib/min-project Abhängigkeit** – rein native Max SDK Header

### Build Steps in VS Code:

1. **Open Terminal** (Ctrl+`) in the project root
2. **Clean Build (empfohlen):**
   ```powershell
   Remove-Item -Recurse -Force build
   cmake -B build -G "Visual Studio 18 2026" -A x64
   cmake --build build --config Debug
   ```
3. **Result:** Compiled `mab_tilde.mxe64` will be in `build/Debug/`

### VS Code Tasks:
- **Build Debug**: Configure and build Debug configuration
- **Build Release**: Build Release configuration (default)

### Debugging in Max MSP:
1. Build Debug: `cmake --build build --config Debug`
2. Open Max, load patch with mab~ object
3. In VS Code: Press F5 → Select "Attach to Max.exe"
4. Select Max.exe process from the list
5. Set breakpoint and test

### Build Troubleshooting:
- **LNK1104 (c74support.lib)**: Nicht mehr relevant – native Build verwendet `MaxAPI.lib` + `MaxAudio.lib`
- **Unknown CMake command "min_project"**: Nicht mehr relevant – kein min-devkit mehr
- **Compiler-Fehler (CLASS_NOFLOAT, std::wstring)**: Verwende `0L` statt `CLASS_NOFLOAT`, `t_symbol*` statt `std::wstring`
- **MSVC 2026 (VS 18)**: Generator `"Visual Studio 18 2026"` verwenden, nicht VS 17

---

## 5. Python Environment Setup

1. **Create Virtual Environment:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Or use setup_env.bat:**
   ```bash
   setup_env.bat
   ```

---

## 6. Required Deliverables

1. **`mab_tilde.cpp`** – C++ Min‑API code for `mab~`, `mc.mab~`, including:
   - Accumulator & shared‑memory mapping
   - Process spawning & clean‑up
   - All Max messages/attributes

2. **`inference_worker.py`** – Autonomous Python script that:
   - Handles IPC communication
   - Loads the TorchScript model
   - Manages device (CPU/GPU) placement
   - Runs the inference loop with lock‑free ring buffer
   - Responds to `dump` and `set` commands

---

**End of Prompt**  
Use this file as the central guide for all coding agents working on the `mab_tilde` project. It defines the required functionality, architecture, and message contract for the MaxMSP external and its Python backend.