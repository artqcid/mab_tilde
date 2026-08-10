# Implementation Plan & Checklist for mab_tilde Project

**Folder:** `doc/`  
**File:** `implementation_plan.md`

---

## 1. Overview
Create a crash‑safe, process‑isolated MaxMSP external family (`mab~`, `mc.mab~`, `mcs.mab~`,
`mab.info`) and its Python backend (`inference_worker.py`) that replaces `nn_tilde`. The solution must:
- Use Windows shared memory and lock‑free SPSC ring buffer for audio block exchange.
- Support CPU/GPU inference, dynamic reload, runtime attribute setting, and model inspection (`dump`).
- Support method-aware inlets/outlets (`encode`/`decode`/`forward`, Latent-Dimensionen) – Phase 3.
- Provide 1:1 message/attribute compatibility with `nn_tilde`.
- Erweiterungen (geplant): `mab.info` (Phase 4), `mc.mab~` (Phase 5), `mcs.mab~` (Phase 6).

---

## 2. First Debug Test Milestone

### Goal: First successful test in Max MSP
The external must be recognized by Max, load without errors, communicate with Python, and terminate cleanly.

### Prerequisites
- Visual Studio 2026 (MSVC 19.51) installed
- Windows SDK 10.0.26100.0 installed
- Python 3.9+ with PyTorch installed in `.venv`
- Max 8+ installed
- A test TorchScript model (`.ts` file) available

### Success Criteria for First Test:
- [x] **External recognized by Max**: No errors when loading the package
- [x] **mab~ object loads**: `[mab~]` can be instantiated in a patch
- [x] **Python server starts**: Background process launches successfully
- [x] **Initial handshake**: C++ and Python exchange shared memory names
- [x] **Shared memory mapped**: Both sides can read/write audio buffers
- [x] **Python signals ready**: `is_python_ready` flag set to true
- [x] **C++ detects ready**: `is_ready` flag becomes true
- [x] **Clean shutdown**: Object deletion terminates Python process cleanly

### Test Procedure:

#### Step 1: Build the External
```powershell
# Clean build from project root
Remove-Item -Recurse -Force build
cmake -B build -G "Visual Studio 18 2026" -A x64
cmake --build build --config Debug
```
**Expected:** Build completes with no errors. Output: `build/Debug/mab~.mxe64`

#### Step 2: Verify Unit Tests Pass
```powershell
# Run all C++ unit tests
.\build\Debug\test_shared_memory_header.exe
.\build\Debug\test_shared_memory_header_compatibility.exe
.\build\Debug\test_message_handlers.exe
.\build\Debug\test_handshake_integration.exe
.\build\Debug\test_multichannel_layout.exe
.\build\Debug\test_anything_handler.exe
.\build\Debug\test_crash_monitoring.exe
.\build\Debug\test_init_worker.exe
.\build\Debug\test_init_worker_thread.exe
.\build\Debug\test_init_worker_thread_comprehensive.exe
.\build\Debug\test_mab_tilde_new.exe
.\build\Debug\test_mab_tilde_free.exe
.\build\Debug\test_mab_tilde_dsp64.exe
.\build\Debug\test_mab_tilde_perform64.exe
.\build\Debug\test_mab_tilde_assist.exe

# Run all Python unit tests
.venv\Scripts\python test/test_block_size_extraction.py -v
.venv\Scripts\python test/test_python_shared_memory.py -v
```
**Expected:** All tests print "All tests passed!" and exit with code 0.

#### Step 3: Install External in Max
1. Create or locate your Max Packages folder (e.g., `Documents/Max 8/Packages/mab_tilde/`)
2. Copy `build/Debug/mab~.mxe64` to the `extensions/` subfolder of the package
3. Create `package-info.json` if not already present:
```json
{
    "name": "mab_tilde",
    "displayName": "mab~",
    "description": "Neural audio processing external",
    "author": "mab_tilde",
    "version": "1.0.0"
}
```

#### Step 4: Create Test Patch
1. Open Max 8
2. Create a new patch
3. Add the following objects:
   - `[mab~ test.ts forward 2048]` - instantiate the external with a test model
   - `[toggle]` - to toggle audio on/off
   - `[dac~]` - audio output
   - `[adc~]` - audio input (or `[noise~]` for testing)
4. Connect: `toggle -> ezdac~` (or `toggle -> ezdac~` with audio input)

#### Step 5: Verify External Loads
1. Save and reopen the patch
2. Check Max Console (`Window > Console`) for errors
3. **Expected:** No errors. Console should show:
   ```
   mab~: Native Max SDK external loaded successfully.
   ```

#### Step 6: Verify Python Handshake
1. Turn on audio (click the toggle)
2. Wait 2-5 seconds for Python to boot and load the model
3. **Expected:** Console shows:
   ```
   mab~: Python worker ready, shared memory mapped successfully.
   ```
4. If Python fails to start, check:
   - Python is installed and in PATH
   - `.venv` has `torch` and `numpy` installed
   - Model path is correct

#### Step 7: Verify Audio Pass-Through
1. With audio on, play audio through the patch
2. **Expected:** Audio passes through `mab~` with minimal latency
3. If Python is not ready yet, audio should still pass through (bypass mode)

#### Step 8: Verify Message Handlers
Send the following messages to `mab~` and verify console output:
1. `enable 0` → Console: `mab~: Audio processing disabled (bypass)`
2. `enable 1` → Console: `mab~: Audio processing enabled`
3. `dump` → Console: Model path, method, buffer size, GPU mode, channels, ready, bypass status
4. `gpu 1` → Console: `mab~: GPU mode set to 1 (requires reload)`
5. `set gpu 0` → Console: `mab~: GPU mode set to 0 (will apply on next load)`
6. `get ready` → Console: `mab~: ready = 1` (or 0 if not ready)
7. `anything test 123` → Console: `mab~: forwarded message: test 123`

#### Step 9: Verify Clean Shutdown
1. Delete the `mab~` object from the patch (select and press Delete)
2. **Expected:** Console shows no errors
3. Check Task Manager to verify no `python.exe` processes remain
4. If Python process lingers, the destructor should terminate it after 500ms timeout

#### Step 10: Verify Crash Recovery
1. While audio is running, force-kill the Python process in Task Manager
2. **Expected:** Console shows:
   ```
   mab~: Python worker crashed. Check VRAM!
   ```
3. Audio should continue in bypass mode (pass-through)
4. Send `reload` message to restart the Python worker
5. **Expected:** Python restarts and handshake completes successfully

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

### 3.8 Method-Aware Inlets/Outlets (`encode`/`decode`/`forward`)
- **Rule:** Inlet-/Outlet-Anzahl folgt der aktiven Inferenz-Methode des Modells, nicht einer fixen `dsp_setup(1)`-Konfiguration.
- **Implementation:** Worker extrahiert `{method}_params = [channels_in, ratio_in, channels_out, ratio_out]` aus dem TorchScript-Modell (Format identisch zu nn_tilde) und schreibt sie vor `signal_ready()` in `SharedMemoryHeader` v2. C++ richtet nach dem Handshake `channels_in` Signal-Inlets und `channels_out` Signal-Outlets ein (Main-Thread via `defer`). Bei `decode` sind die Inlets Latent-Streams (`latent_size = channels_in`), bei `encode` die Outlets. Latent-Buffer im Shared Memory nach Ratios dimensioniert (Phase 3).

### 3.9 Prozess-Isolierte Modell-Inspektion (`mab.info`)
- **Rule:** `mab.info` darf **kein** PyTorch in den Max-Prozess laden (anders als `nn.info`).
- **Implementation:** `mab.info` startet den Worker im `--query`-Modus, der das Modell lädt, Metadaten (Methoden, `channels_in/out`, Ratios, Attribute) als JSON/Shared-Memory-Dict liefert und sich beendet (Phase 4).

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

#### 1.2 Asynchronous Initialization ✅ (COMPLETE)
- [x] Add `#include <thread>` and `#include <atomic>` to mab_tilde.cpp
- [x] Create `init_worker_thread()` function to run in background thread
- [x] Spawn detached `std::thread` in `mab_tilde_new()` that launches Python
- [x] Use `long` (not `std::atomic<bool>`) for `is_ready` flag (C-Struct safety)
- [x] Use `long` for `is_bypass` flag
- [x] `mab_tilde_new()` returns immediately after spawning background thread
- [x] Audio processing starts in bypass mode until `is_ready` becomes true
- [x] Store Python process handle (`HANDLE`) in struct for clean termination
- [x] Generate unique instance ID for shared memory naming

#### 1.3 Shared Memory Management (Handshake Protocol) ✅ (COMPLETE)
- [x] Define `SharedMemoryHeader` struct in C++ (C-compatible, no C++ objects):
  - `uint32_t magic` (0x4D414254 = 'MABT')
  - `uint32_t version` (1)
  - `uint32_t block_size` (samples per block)
  - `uint32_t num_channels` (1 for mab~, up to 16 for mc.mab~)
  - `uint32_t input_offset` (byte offset to input buffer)
  - `uint32_t output_offset` (byte offset to output buffer)
  - `long is_input_ready` (atomic flag, set by Python)
  - `long is_output_ready` (atomic flag, set by Python)
  - `long is_python_ready` (atomic flag, set by Python)
  - `long shutdown_flag` (atomic flag, C++ tells Python to die)
- [x] C++ polls for Python's ready signal via named event (`OpenEventW`)
- [x] C++ maps existing shared memory using `OpenFileMappingW`
- [x] C++ maps view using `MapViewOfFile`
- [x] Validate shared memory header (magic number check)
- [x] Store mapped pointers in struct for audio callback access
- [x] Unmap and close handles in destructor

#### 1.4 Multi-Channel Memory Layout ✅ (COMPLETE)
- [x] Implement contiguous layout: `[num_channels, block_size]`
- [x] Calculate buffer sizes: `num_channels * block_size * sizeof(float)`
- [x] Provide channel count parameter to Python via handshake
- [x] Support dynamic channel count for `mc.mab~`

#### 1.5 Real-Time Safe Synchronization ✅ (COMPLETE)
- [x] Replace blocking events with `long` atomic flags (volatile):
  - `is_input_ready` - set by Python when input block is ready
  - `is_output_ready` - set by Python when output block is processed
- [x] Audio callback (`dsp64`) uses non-blocking poll:
  ```cpp
  if (x->header->is_input_ready == 0) {
      // Copy input to shared memory
      x->header->is_input_ready = 1;
  }
  ```
- [x] Bypass mode: when not ready, pass audio through unchanged
- [x] No `WaitForSingleObject`, mutexes, or blocking calls in audio thread

#### 1.6 Process Lifecycle ✅ (COMPLETE)
- [x] Parse Max arguments (`model.ts`, `method`, `buffer_size`, `channels`).
- [x] Launch `python inference_worker.py` with appropriate args in background thread.
- [x] Store process handle for clean termination.
- [x] Implement graceful shutdown (`shutdown_flag` in shared memory).
- [x] Handle process startup failure gracefully (stay in bypass mode).

#### 1.7 Message Handlers ✅ (COMPLETE)
- [x] `enable` - toggle bypass mode
- [x] `gpu` - request GPU/CPU switch
- [x] `reload` - reload model (restarts Python process)
- [x] `dump` - request model info
- [x] `set` - set attribute
- [x] `get` - get attribute value
- [x] `method` - change inference method
- [x] `load` - change model dynamically
- [x] Forward generic `anything` messages to Python.

#### 1.8 Memory Cleanup ✅ (COMPLETE)
- [x] Unmap shared memory, close handles, terminate Python process.
- [x] Join background thread if still running.

### Phase 2 – Python Backend (with Critical Architecture)

#### 2.1 Argument Parsing ✅ (COMPLETE)
- [x] Read command-line args: model path, method, buffer size, GPU flag
- [x] Add shared memory name parameter (from C++)
- [x] Add instance ID parameter (for unique naming)
- [x] Add channel count parameter

#### 2.2 Shared Memory Creation (Handshake Protocol) ✅ (COMPLETE)
- [x] Create shared memory segments using `CreateFileMappingW`
- [x] Write header with magic, block_size, num_channels, offsets
- [x] Signal C++ that shared memory is ready (via named event)
- [x] Validate header structure matches C++ definition exactly
- [x] Use `c_long` for atomic flags (matches C++ `long`)

#### 2.3 Multi-Channel Memory Layout ✅ (COMPLETE)
- [x] Allocate contiguous buffer: `num_channels * block_size * 4` bytes
- [x] Create NumPy view: `np.frombuffer(shared_mem, dtype=np.float32).reshape(num_channels, block_size)`
- [x] Create PyTorch tensor: `torch.from_numpy(np_array)` (zero-copy)

#### 2.4 Ring Buffer (Control Messages) ✅ (COMPLETE)
- [x] Implement `LockFreeRingBuffer` class to receive C++ messages.
- [x] Parse incoming messages (`enable`, `gpu`, `reload`, `dump`, `set`, `get`, `method`, `load`).

#### 2.5 Model Management ✅ (COMPLETE)
- [x] Load TorchScript model with `torch.jit.load`.
- [x] Move model to CPU or CUDA based on flag.
- [x] Support `reload` to re-load model on demand.
- [x] Extract model's expected block size from input shape.

#### 2.6 Inference Loop ✅ (COMPLETE)
- [x] Poll for input ready flag (non-blocking)
- [x] Run `torch.no_grad()` inference on block.
- [x] Write processed block back to output shared memory.
- [x] Set output ready flag.

#### 2.7 Runtime Attributes ✅ (COMPLETE)
- [x] Store mutable attributes in a dict.
- [x] Parse `set <name> <value>` messages.
- [x] Parse `get <name>` messages and return values.

#### 2.8 Model Inspection (`dump`) ✅ (COMPLETE)
- [x] Output model metadata (methods, shapes, attributes) to stdout.

#### 2.9 Graceful Exit ✅ (COMPLETE)
- [x] Monitor global `running` flag to break loop and exit.
- [x] Clean up shared memory handles.

---

### Phase 3 – Method-Aware Processing & Latent Inlets (encode/decode/forward)

**Status:** 🔲 NICHT GESTARTET – aktueller Stand: `dsp_setup(x, 1)` fixiert, keine Methoden-Metadaten im Header.

**Befund (Bug „keine latent inlets bei `decode`"):**
Beim Laden von `D:\AI-Models\ts models\musicnet.ts` (AFTER / `VariationalScriptedRAVE`) mit
`method decode` erscheinen keine latenten Inlets, nur Audio-In/Out – ohne Fehlermeldung.
Ursachen (verifiziert am Quellcode):
1. `mab_tilde_new()` ruft fix `dsp_setup(x, 1)` + 1 Signal-Outlet auf (`mab_tilde.cpp:138`).
   Die Inlet-/Outlet-Anzahl hängt nicht von der Methode ab.
2. Der Worker liest die Methoden-Metadaten nie und überträgt sie nicht an C++:
   `SharedMemoryHeader` kennt nur `block_size`/`num_channels`. Das Modell liefert aber
   `decode_params = [16, 2048, 1, 1]` und `encode_params = [1, 1, 16, 2048]` (Tensor).
   Format identisch zu nn_tilde (`get_method_params` → `[channels_in, ratio_in, channels_out, ratio_out]`).
3. `mab_tilde_method()` leitet `method` nicht an Python weiter (nur `post`); der Worker-Handler
   `method` druckt nur, er wechselt die Inferenzfunktion nicht.
4. `infer_block()` ruft hartcodiert `model(tensor)` auf – nie `model.encode()` / `model.decode()`.

**Konsequenz für `musicnet.ts` mit `decode`:** Modell erwartet 16 Latent-Kanäle
(`channels_in=16`, `ratio_in=2048`) und liefert 1 Audiokanal (`channels_out=1`, `ratio_out=1`).
Zielzustand: **16 Latent-Inlets + 1 Audio-Outlet** (bei `encode` umgekehrt).

#### Task 3.1 – Model-Method-Metadaten-Handshake (Python + C++)
- [ ] Worker liest nach dem Laden alle `{method}_params`-Tensoren
      (`[channels_in, ratio_in, channels_out, ratio_out]`) für die vorhandenen Methoden
      (`encode`/`decode`/`forward`) via `model._c.get_method(name)` + `model.attr(name + "_params")`.
- [ ] `SharedMemoryHeader` auf Version 2 erweitern (C++ + ctypes-`_fields_`):
  - [ ] `uint32_t channels_in` / `uint32_t channels_out`
  - [ ] `uint32_t input_ratio` / `uint32_t output_ratio`
  - [ ] `uint32_t latent_size` (= `channels_in` bei decode, `channels_out` bei encode)
  - [ ] `char method[64]` (aktive Methode)
- [ ] Python schreibt diese Felder vor `signal_ready()` in den Header.
- [ ] C++ `init_worker()` liest die Felder nach `MapViewOfFile` aus und speichert sie im Struct.
- [ ] `test_shared_memory_header_compatibility` auf v2 aktualisieren.

#### Task 3.2 – Latent-Buffer & Ratio-Handling (Python)
- [ ] Shared Memory um Latent-Bereiche erweitern: Eingabe `channels_in × frames_in × 4B`,
      Ausgabe `channels_out × frames_out × 4B`; `frames` aus `block_size` und Ratios abgeleitet
      (decode: 1 Latent-Frame pro `ratio_in`=2048 Audio-Samples).
- [ ] Buffergröße dynamisch nach Methoden-Params dimensionieren (nicht mehr fix `num_channels × block_size`).
- [ ] `infer_block()` → Methoden-Dispatch: `forward`→`model(x)`, `encode`→`model.encode(x)`,
      `decode`→`model.decode(z)` (bei AFTER optional `from_forward` aus `forward_params` ableiten).
- [ ] Ratio-Handling v1: Latent-Frame über das Hop-Fenster halten (nearest-hold);
      v2: Interpolation wie nn_tilde – Detail im Implementierungsschritt verifizieren.
- [ ] `method <name>`-Message im Worker: Methode wirklich wechseln, Metadaten neu in den Header
      schreiben (Bestätigung an C++), nicht nur printen.

#### Task 3.3 – Dynamische Inlets/Outlets (C++, nativer Max-SDK)
- [ ] Inlets = `channels_in`, Outlets = `channels_out` der aktiven Methode.
- [ ] Nach Handshake `dsp_setup(x, n_inlets)` + `outlet_new(x, "signal")`.
      **Max-Hauptthread-Regel:** Umbau nur auf dem Main-Thread → vom Init-Thread per `defer()`/
      `schedule` auf den Main-Thread posten (Argumente via `sysmem_newptr`-Struktur, `defer`
      übernimmt den Free).
- [ ] Fallback, falls Runtime-Umbau im nativen SDK instabil: Recreate/Reconnect-Ansatz prüfen;
      Mindestziel: Inlets korrekt sobald Modell geladen (Bypass vorher mit Stille, kein Crash).
- [ ] Inlet-/Outlet-Labels wie nn_tilde: `{method}_input_labels`/`{method}_output_labels` aus dem
      Modell lesen, sonst `(signal) latent input i` / `(signal) audio output i`.
- [ ] `assist` auf dynamische Inlets/Outlets anpassen.

#### Task 3.4 – Verifikation
- [ ] `[mab~ musicnet.ts decode 2048]` → 16 Latent-Inlets, 1 Audio-Outlet, keine Dropouts.
- [ ] `forward` → 1 Inlet/1 Outlet wie bisher.
- [ ] `encode` → 1 Audio-Inlet, 16 Latent-Outlets.
- [ ] Methodenwechsel zur Laufzeit per `method decode`.
- [ ] Python-Unit-Test „Metadaten-Extraktion" (analog `test_block_size_extraction.py`).

---

### Phase 4 – `mab.info` (Modell-Inspektor, analog `nn.info`)

**Status:** 🔲 NICHT GESTARTET

**Referenz:** nn_tilde `src/frontend/maxmsp/nn.info/nn.info.cpp`.
**Ziel:** `mab.info` als **prozessisoliertes** Gegenstück zu `nn.info`. Wichtigster Unterschied zu
nn_tilde: **kein PyTorch im Max-Prozess** – `mab.info` nutzt denselben Python-Worker wie `mab~`.

#### Design
- Nicht-Signal-External, 1 Inlet (Messages), Outlets:
  1. `model path` (symbol)
  2. `available methods` (symbol)
  3. `available attributes` (symbol)
  4. `processing parameters` (symbol + ints)
  5. `dict output` (dictionary)
  6. `available models for download` (dictionary) – optional (IRCAM-API, evtl. out of scope)
- **Query-Modus:** `mab.info` startet den Worker mit `--query <model>`; der Worker lädt das Modell,
  extrahiert `{method}_params`, `{method}_input_labels`/`_output_labels` und settable attributes,
  druckt ein JSON-Dict auf stdout und beendet sich (stdout wird wie beim Worker ins Log umgeleitet
  und von C++ geparst). Alternative für Live-Binding: Metadaten über Shared-Memory-Dict austauschen
  und auf `get`-Messages antworten.
- **Messages (nn.info-kompatibel):** `set <model>`, `bang`, `dump`, `path`, `methods`, `attributes`,
  `parameters <method|attribute>`, `dump_dict`, `dict <name>`.

#### Tasks
- [ ] Shared Worker-Launch aus mab~ in gemeinsamen Helper refactorn
      (`worker_launch.cpp`/`.h`: `resolve_worker_dir`, venv-Python, `CreateProcessW`,
      Log-Umleitung) – Wiederverwendung durch `mab~`, `mc.mab~`, `mcs.mab~`, `mab.info`.
- [ ] `--query`-Modus im `inference_worker.py` (JSON-Dict auf stdout, Exit 0).
- [ ] C++ `mab.info`: `model.ts`-Argument, Launch + stdout-Parse (blockierend OK, kein Audio).
- [ ] Outlets 1–5 füllen; `dict`-Binding über Max-Dictionary.
- [ ] Build + Deploy `mab.info.mxe64` ins Max-9-Package (`externals/`).
- [ ] Test: `[mab.info musicnet.ts]` → `bang` listet `decode; encode; forward`, 16 Latent, 1 Audio, Attribute.

---

### Phase 4.5 – Real-Time-Schutz (ASIO-XRun-Prävention) 🟢 FERTIG

**Status:** 🟢 FERTIG – Voraussetzung für Phase 5/6. Ergänzt nach dem gemeldeten
ASIO-Buffer-Overflow im `decode`-Modus (der Worker verteilte sich über alle
Kerne und kollidierte mit dem Audio-Thread).

**Ziel:** Der Worker darf den Audio-/ASIO-Thread von Max nie verhungern lassen;
die Inferenz darf sich nie über alle Kerne verteilen.

#### Implementiert
- **worker_launch.cpp:** Nach `CreateProcessW` → `SetPriorityClass(pi.hProcess,
  BELOW_NORMAL_PRIORITY_CLASS)` + `SetProcessAffinityMask(pi.hProcess,
  sysMask & ~1)` (alle Kerne außer Core 0, Guard für Ein-Kern-Systeme).
- **inference_worker.py:** `cores`-Argument (Default 1) setzt vor dem ersten
  Modell-Load `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS` und
  `torch.set_num_threads(cores)`.
- **CPU-only-Gate:** `cores` greift NUR im CPU-Modus (`gpu 0`); im GPU-Modus
  inaktiv (CUDA nutzt keine OpenMP/MKL-Threads). Re-Apply bei Wechsel auf CPU.
- **mab_tilde.cpp:** Optionale 6. Position `cores`
  (`[mab~ model method bufsize gpu #channels cores]`), per
  `worker_launch`-Commandline durchgereicht. Abwärtskompatibel (Default 1).
  (`mab.info` benötigt kein `cores` – `--query`-Modus skippt Thread-Limiting.)

#### Pflicht für Phase 5/6
- `mc.mab~` und `mcs.mab~` dürfen NUR den gemeinsamen `worker_launch`-Pfad
  verwenden und erben Priorität/Affinität/Thread-Einstellungen. Kein eigener
  Prozess-Start in den neuen Objekten.

---

### Phase 4.6 – nn_tilde-Paritäts-Delta (Modell-Parameter/Optionen) 🟢 GROSSTEILS FERTIG

**Status:** 🟢 P1–P6 FERTIG, P7 offen (Phase-5/6-abhängig), P8–P11 = bestehende Phasen 5/6.

**Quelle:** `doc/nn_tilde_parity.md` (verifiziertes Paritäts-Delta gegen `thirdParty\nn_tilde`).
**Geordnet nach Priorität/Dependency:** unten zuerst ist die Grundlage für alles darüber.

| # | Punkt | Status | Umsetzung |
|---|-------|--------|-----------|
| P1 | **Modell-Attribute-Passthrough** (`set`/`get` → Worker → `setattr` auf Modell; Typ-Koerzierung bool/int/float/str via `_c.get_attribute`-Typ) | ✅ | Worker `apply_model_attribute`/`coerce_value`; C++ forwardet `set <attr> <vals...>`/`get <attr>` (lokal bleiben nur `gpu`/`buffer_size`/`channels`) |
| P2 | anything-Sub-Commands **`get_attributes`**/`get_methods`; **`dump` an Worker** (volle Metadaten) | ✅ | Worker-Handler `get_attributes`/`get_methods`; C++ `dump` forwardet zusätzlich an Worker |
| P3 | **`gpu` als echter Setter** (Message an Worker → Modell auf neuem Device neu laden, `_limit_inference_threads`-Re-Apply bei CPU) | ✅ | Worker `gpu`-Handler lädt Modell neu + re-applied Attribute |
| P4 | **`buffer size 0`-Semantik** (Auto: `block_size = max(ratios)`, Low-Latency) | ✅ | `compute_layout` deckt das bereits ab; dokumentiert |
| P5 | **Void-Modus** (`mab~ void <in> <out> <bufsize>` → reiner Passthrough, N Inlets/Outlets, kein Worker) | ✅ | C++ `mab_tilde_new` parst `"void"`, `dsp_resize` + Outlets auf Main-Thread |
| P6 | **`print_available_models`**/`download`/`delete` (IRCAM-API) | ✅ | Worker: lokale Modelle + Remote (try/except, offline-sicher); nur `.ts` innerhalb Modell-Ordnern löschbar |
| P7 | **`track_buffers` + buffer~-Support** (`BufferManager`/`buffer_reference` analog `buffer_tools.h`) | 🔲 OFFEN | braucht c74-min-`buffer_reference`; Phase-5/6-abhängig, erfordert Max-Runtime-Test |
| P8 | **`mc.mab~`** (`multichanneloutputs`/`inputchanged`, `channel_map`, `chans`) | 🔲 OFFEN | → Phase 5 |
| P9 | **`mcs.mab~`** (`n_batches`, Batch-Inferenz) | 🔲 OFFEN | → Phase 6 |
| P10 | Argument-Overrides (Arg4/5 Inlet-/Outlet-Anzahl, mcs `n_batches`) | 🔲 OFFEN | → Phase 5/6 |
| P11 | `mab.info`: `get_available_models`/`download`/`delete`-Messages | 🔲 OFFEN | → Phase-4-Follow-up |

---

### Phase 5 – `mc.mab~` (Multichannel, analog `mc.nn~`)

**Status:** 🔲 NICHT GESTARTET

**Referenz:** nn_tilde `src/frontend/maxmsp/mc.nn_tilde/mc.nn_tilde.cpp`
(`mc_operator<>`, `multichanneloutputs`/`inputchanged`, `channel_map`, `chans`-Attribut).

**Ziel:** `mc.mab~` = `mab~` mit Multichannel-Signal-Inlets/Outlets (`mc.`-Konvention):
jede Modell-Eingangsgruppe als `mc.`-Inlet, `chans`-Attribut für fixe Out-Channels.

#### Tasks
- [ ] Zusätzliche Klassen-Registrierung `mc.mab~` in `ext_main`; gemeinsame Kernlogik
      (Worker-Launch + IPC) über die Basis-/Shared-Struct.
- [ ] Native-SDK-Äquivalent zu `mc_operator<>`:
  - [ ] `class_addmethod(c, (method)simplemc_multichanneloutputs, "multichanneloutputs", A_CANT, 0)`
  - [ ] `class_addmethod(c, (method)simplemc_inputchanged, "inputchanged", A_CANT, 0)`
        → `update_channel_map(index, count)` + `wait_for_buffer_reset`
  - [ ] Multichannel-Inlets/Outlets (Prüfung: `"multichannelsignal"`-Typ im nativen SDK).
- [ ] Shared Memory: statt fixem `num_channels` eine Channel-Map `channel_map[index]=count`;
      Python baut Batches `(batch, channels_in, block_size)` und ruft `model.<method>`.
- [ ] `chans <n>`-Attribut = fixe Output-Channel-Anzahl (analog `mc.nn~`).
- [ ] Phase-3-Metadaten (Latent) mit Multichannel kombinieren: decode → 1 `mc.`-Latent-Inlet
      (16-Kanal) → 1 Audio-`mc.`-Outlet.
- [ ] Verifikation: `[mc.mab~ musicnet.ts decode 2048]` mit `[noise~ 16]` → Audio-Outlet.

---

### Phase 6 – `mcs.mab~` (Batched Multichannel, analog `mcs.nn~`)

**Status:** 🔲 NICHT GESTARTET

**Referenz:** nn_tilde `src/frontend/maxmsp/mcs.nn_tilde/mcs.nn_tilde.cpp`.

**Ziel:** `mcs.mab~` = N parallele Batches: `n_batches` Inlets, jeder Inlet ein Multichannel-Batch
mit `channels_in` Dims; das Modell wird auf allen Batches gleichzeitig ausgeführt (Batch-Dim).
Sinnvoll für AFTER/RAVE mit fixem Latent (mehrere parallele Stimmen).

#### Tasks
- [ ] `n_batches` (2. Argument) Inlets, `n_batches` Outlets.
- [ ] `update_method()` überschreiben: `m_model_in/out` aus `{method}_params`,
      `m_out_channels` aus `channels_out`.
- [ ] `multichanneloutputs` → `m_out_channels`; `inputchanged` → Batch-Map aktualisieren.
- [ ] Shared Memory: Eingabe `(n_batches × channels_in × block_size)`,
      Ausgabe `(n_batches × channels_out × block_size)`; Python:
      `input.view(n_batches, channels_in, block_size)` → `model.<method>(x)`.
- [ ] Verifikation: `[mcs.mab~ musicnet.ts encode 4 2048]` → 4 Inlets, je 16-Latent-Outlets.

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

**Version 1 (aktueller Stand, Phase 1–2):**
```cpp
// C-compatible struct (no C++ objects, no std::atomic)
struct SharedMemoryHeader {
    uint32_t magic;           // 0x4D414254 ('MABT')
    uint32_t version;         // 1
    uint32_t block_size;      // samples per block
    uint32_t num_channels;    // 1 for mab~, up to 16 for mc.mab~
    uint32_t input_offset;    // bytes to input buffer
    uint32_t output_offset;   // bytes to output buffer
    uint32_t control_offset;  // bytes to control ring buffer
    long is_input_ready;      // atomic flag (volatile)
    long is_output_ready;     // atomic flag (volatile)
    long is_python_ready;     // atomic flag (volatile)
    long shutdown_flag;       // atomic flag (C++ tells Python to die)
};
```

**Version 2 (geplant, Phase 3 – Methoden-Metadaten für Latent-Inlets):**
```cpp
struct SharedMemoryHeader {
    uint32_t magic;           // 0x4D414254 ('MABT')
    uint32_t version;         // 2
    uint32_t block_size;      // samples per block
    uint32_t num_channels;    // 1 for mab~, up to 16 for mc.mab~
    uint32_t channels_in;     // method: model input channels (decode: latent_size)
    uint32_t channels_out;    // method: model output channels (decode: 1)
    uint32_t latent_size;     // = channels_in (decode) / channels_out (encode)
    uint32_t input_ratio;     // e.g. RAVE decode: 2048
    uint32_t output_ratio;    // e.g. RAVE decode: 1
    char method[64];          // active method: forward/encode/decode
    uint32_t input_offset;    // bytes to input buffer
    uint32_t output_offset;   // bytes to output buffer
    uint32_t control_offset;  // bytes to control ring buffer
    long is_input_ready;      // atomic flag (volatile)
    long is_output_ready;     // atomic flag (volatile)
    long is_python_ready;     // atomic flag (volatile)
    long shutdown_flag;       // atomic flag (C++ tells Python to die)
};
```

// Lock-free SPSC ring buffer for control messages
struct ControlRingBuffer {
    long head;                           // Written by C++ (producer)
    long tail;                           // Written by Python (consumer)
    char messages[256][256];             // Message buffer (256 messages, 256 bytes each)
};
```
};
```

### 6.2 Audio Callback (dsp64) - Lock-Free Implementation
```cpp
void mab_tilde_perform64(t_mab_tilde* x, t_object* dsp64, double** ins, long numins, double** outs, long numouts, long sampleframes, long flags, void* userparam) {
    long n = sampleframes;
    long channels = x->header ? x->header->num_channels : 1;
    if (channels < 1) channels = 1;
    if (channels > MAX_CHANNELS) channels = MAX_CHANNELS;

    // Crash monitoring: check if Python process is still alive (non-blocking)
    if (x->is_ready && x->python_process) {
        DWORD exitCode = 0;
        if (GetExitCodeProcess(x->python_process, &exitCode)) {
            if (exitCode != STILL_ACTIVE) {
                post("mab~: Python worker crashed. Check VRAM!");
                InterlockedExchange(&x->is_ready, 0);
                InterlockedExchange(&x->is_bypass, 1);
                // Clean up shared memory...
                return;
            }
        }
    }

    // Bypass mode: pass audio through unchanged when not ready
    if (!x->is_ready || x->is_bypass || !x->header) {
        for (long ch = 0; ch < numouts && ch < channels; ch++) {
            double* in = ins[ch < numins ? ch : 0];
            double* out = outs[ch];
            for (long i = 0; i < n; i++) {
                out[i] = in[i];
            }
        }
        return;
    }

    // Write Input to Shared Memory (multi-channel: [num_channels, block_size])
    if (x->header->is_input_ready == 0) {
        for (long ch = 0; ch < channels; ch++) {
            double* in = ins[ch < numins ? ch : 0];
            float* shm_in = x->p_input + ch * x->header->block_size;
            for (long i = 0; i < n && i < (long)x->header->block_size; i++) {
                shm_in[i] = (float)in[i];
            }
        }
        InterlockedExchange(&x->header->is_input_ready, 1);
    }

    // Read Output from Shared Memory
    if (x->header->is_output_ready == 1) {
        for (long ch = 0; ch < channels; ch++) {
            double* out = outs[ch < numouts ? ch : 0];
            float* shm_out = x->p_output + ch * x->header->block_size;
            for (long i = 0; i < n && i < (long)x->header->block_size; i++) {
                out[i] = (double)shm_out[i];
            }
        }
        InterlockedExchange(&x->header->is_output_ready, 0);
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
**Status:** ✅ COMPLETE

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
**Status:** ✅ COMPLETE

**Tasks:**
1. ✅ Define `SharedMemoryHeader` struct (C-compatible, no C++ objects)
2. ✅ Implement `OpenFileMappingW` + `MapViewOfFile` in `init_worker()`
3. ✅ Validate header magic number
4. ✅ Store mapped pointers in struct
5. ✅ Implement cleanup in `mab_tilde_free()`

### Phase 2.1 – Argument Parsing (Python)
**Status:** ✅ COMPLETE

**Tasks:**
1. ✅ Add `shm_name` argument to argparse
2. ✅ Add `instance_id` argument to argparse
3. ✅ Add `num_channels` argument to argparse
4. ✅ Add `block_size` argument to argparse (optional, defaults to 512)

### Phase 2.2 – Shared Memory Creation (Handshake Protocol)
**Status:** ✅ COMPLETE

**Tasks:**
1. ✅ Verify `SharedMemoryHeader` struct matches C++ definition exactly (same field order, same types)
2. ✅ Ensure `is_input_ready`, `is_output_ready`, `is_python_ready` use `c_long` (maps to `long` in C++)
3. ✅ Create named event (`CreateEventW`) for ready signal
4. ✅ Signal C++ via `SetEvent` after header initialization
5. ✅ Verify shared memory name format matches C++ (`MabSharedMem_{instance_id:08X}`)
6. ✅ Verify event name format matches C++ (`MabReadyEvent_{instance_id:08X}`)

### Phase 2.3 – Inference Loop (Python)
**Status:** ✅ COMPLETE

**Tasks:**
1. ✅ Implement proper polling loop with `time.sleep(0.001)` for low CPU
2. ✅ Check `is_input_ready` flag (non-blocking)
3. ✅ Run `torch.no_grad()` inference on input block
4. ✅ Write output to shared memory buffer
5. ✅ Set `is_output_ready` flag
6. ✅ Clear `is_input_ready` flag

---

## 9. Implementation Order (Recommended)

1. ✅ **Phase 1.2** (C++ Background Thread) - Spawn Python process, poll for ready event
2. ✅ **Phase 1.3** (C++ Shared Memory) - OpenFileMappingW, MapViewOfFile, validate header
3. ✅ **Phase 2.1** (Python Args) - Add shm_name, instance_id, num_channels arguments
4. ✅ **Phase 2.2** (Python Shared Memory) - Verify header struct matches, signal ready
5. ✅ **Phase 2.3** (Python Inference Loop) - Implement polling and pass-through
6. ✅ **Phase 1.5** (Audio Callback) - Update perform64 with shared memory I/O
7. ✅ **Phase 1.6** (Process Lifecycle) - Parse args, store handle, graceful shutdown
8. ✅ **Phase 1.8** (Memory Cleanup) - Unmap, close handles, terminate process
9. ✅ **Phase 1.7** (Message Handlers) - enable, gpu, reload, dump, set, get, method, load

---

## 10. Current Implementation Status Summary

### ✅ COMPLETE - All Core Phases Implemented

| Phase | Component | Status | Notes |
|-------|-----------|--------|-------|
| 1.2 | C++ Background Thread | ✅ | `init_worker()` spawns Python, waits for ready event |
| 1.3 | C++ Shared Memory | ✅ | `OpenFileMappingW`, `MapViewOfFile`, header validation |
| 2.1 | Python Args | ✅ | argparse with shm_name, instance_id, num_channels |
| 2.2 | Python Shared Memory | ✅ | `CreateFileMappingW`, `SetEvent`, header initialization |
| 2.3 | Python Inference Loop | ✅ | Non-blocking polling, `torch.no_grad()` inference |
| 1.5 | Audio Callback | ✅ | Lock-free `perform64` with shared memory I/O |
| 1.6 | Process Lifecycle | ✅ | `CreateProcessW`, handle storage, graceful shutdown |
| 1.8 | Memory Cleanup | ✅ | `UnmapViewOfFile`, `CloseHandle`, terminate process |
| 1.7 | Message Handlers | ✅ | enable, gpu, reload, dump, set, get, method, load |

### ⚠️ PARTIALLY COMPLETE - Missing Features

| Feature | Status | Notes |
|---------|--------|-------|
| `anything` message forwarding | ✅ | Implemented - `mab_tilde_anything()` forwards messages via lock-free ring buffer |
| `method` message | ⚠️ | Nur `post` in C++, kein Forwarding an Python; Worker wechselt die Methode nicht (Phase 3) |
| Multi-channel (`mc.mab~`) | ⚠️ | Nur `num_channels`-Argument + `[num_channels, block_size]`-Layout; **kein** echtes `mc.`-External (Phase 5) |
| Method-aware inlets/outlets (Latent) | ❌ | `dsp_setup(x, 1)` fixiert; keine `{method}_params`-Metadaten im Header (Phase 3) |
| Control ring buffer | ✅ | `ControlRingBuffer` integrated in shared memory, C++ enqueues, Python dequeues |
| Model block size extraction | ✅ | `extract_block_size()` function added, extracts from model graph |
| Crash monitoring | ✅ | `GetExitCodeProcess()` check in perform64, auto-fallback to bypass on crash |

### 🔲 NICHT GESTARTET - Geplante Phasen (dieses Dokument)

| Phase | Komponente | Analog zu nn_tilde | Kern |
|-------|-----------|--------------------|------|
| 3 | Method-aware processing & Latent-Inlets | `update_method()`/`get_method_params` | Header v2, Latent-Buffer, dynamische Inlets/Outlets, `method`-Dispatch |
| 4 | `mab.info` | `nn.info` | Prozessisolierter Modell-Inspektor (`--query`-Modus), keine torch-Lib im Max-Prozess |
| 5 | `mc.mab~` | `mc.nn~` | `multichanneloutputs`/`inputchanged`, `channel_map`, `chans`-Attribut |
| 6 | `mcs.mab~` | `mcs.nn~` | `n_batches` Inlets, Batch-Inferenz `(batch, channels_in, block_size)` |

### ✅ COMPLETE - All Unit Tests

| Test | Status | Notes |
|------|--------|-------|
| `test_shared_memory_management.cpp` | ✅ | Created - tests shared memory creation/validation |
| `test_init_worker.cpp` | ✅ | Exists - tests function signature |
| `test_init_worker_thread.cpp` | ✅ | Exists - tests thread function |
| `test_mab_tilde_new.cpp` | ✅ | Exists - tests object creation |
| `test_mab_tilde_free.cpp` | ✅ | Exists - tests cleanup |
| `test_mab_tilde_perform64.cpp` | ✅ | Exists - tests audio callback |
| `test_python_shared_memory.py` | ✅ | Exists - tests Python shared memory |
| `test_shared_memory_header_compatibility.cpp` | ✅ | **NEW** - Tests C++ and Python header struct compatibility |
| `test_message_handlers.cpp` | ✅ | **NEW** - Tests all message handlers (enable, gpu, reload, dump, set, get, method, load) |
| `test_handshake_integration.cpp` | ✅ | **NEW** - Integration test for C++/Python handshake |
| `test_multichannel_layout.cpp` | ✅ | **NEW** - Tests multi-channel memory layout |
| `test_anything_handler.cpp` | ✅ | **NEW** - Tests anything message forwarding |
| `test_crash_monitoring.cpp` | ✅ | **NEW** - Tests crash detection and state transition |
| `test_block_size_extraction.py` | ✅ | **NEW** - Tests Python block size extraction from model |

---

*End of Implementation Plan & Checklist*
