# Workspace Agent Prompt – Elite C++ (MaxMSP Min-API) & Python (PyTorch, CUDA, Multiprocessing) Developer

**Role:**  
You are an elite developer specialized in C++ for MaxMSP (Min-API) and Python (PyTorch, CUDA, Multiprocessing). Your mission is to implement the complete MaxMSP external package `mab~`, `mc.mab~` (and the inspection tool `mab.info`) along with the associated Python backend `inference_worker.py`.

> **Für alle Coding-Agents (opencode, Continue, Cloud-Modelle via MCP):**
> Diese Datei ist die zentrale Anleitung und wird über `AGENTS.md` automatisch
> geladen. Lies sie vollständig, bevor du Änderungen vornimmst. Für präzise
> Fragen zum Projektcode (Signaturen, Konstanten, Message-Handler) nutze das
> SQLite-RAG über den MCP-Server – siehe Abschnitt 6.

## Project Goal
Create a crash‑safe, process‑isolated MaxMSP external that replaces `nn_tilde` and makes TorchScript models (`.ts`, e.g. RAVE, AFTER) work **absolutely crash‑safe** under Windows. The original `nn_tilde` crashes on Windows due to `libtorch` heap bugs in threads, so we use **process isolation via Shared Memory (Memory‑Mapped Files) and Lock‑Free SPSC Ring Buffer**.

---

## 1. MaxMSP Objects & Syntax Parity to `nn_tilde`

### `mab~` (Single Channel / Stream)
- **Arguments:** `[mab~ model_name.ts (method_name) (buffer_size)]`
- **Example:** `[mab~ model.ts decode 2048]`
- **Default method:** `forward`
- Dynamically support typical methods (e.g., `encode`, `decode`, `forward`) as in RAVE.
- **Method-Aware Inlets/Outlets (Phase 3):** Inlet-/Outlet-Anzahl folgt `{method}_params =
  [channels_in, ratio_in, channels_out, ratio_out]` aus dem TorchScript-Modell (identisch zu
  nn_tilde). `decode` → `channels_in` Latent-Inlets + `channels_out` Audio-Outlets;
  `encode` → Audio-Inlet + Latent-Outlets. Metadaten kommen über `SharedMemoryHeader` v2 vom
  Worker (vor `signal_ready()` geschrieben); der IO-Umbau läuft über `mab_tilde_apply_io`
  auf dem Max-Main-Thread (`t_qelem`). Status: 🟢 implementiert (Phase 3, Task 3.4-Max-Test
  offen), siehe `doc/implementation_plan.md` Phase 3.

### `mc.mab~` (Multi‑Channel)
- Processes Max 8+ multi-channel signals in batch mode (similar to `mc.nn~`) to run multiple tracks in parallel through the model.
- **Status:** 🔲 geplant (Phase 5) – aktuell nur `num_channels`-Argument + `[num_channels, block_size]`-Layout, kein echtes `mc.`-External.

### `mcs.mab~` (Batched Multi‑Channel)
- `n_batches` Inlets, jeder Inlet ein Multichannel-Batch (`channels_in` Dims); Batch-Inferenz `(batch, channels_in, block_size)`. Analog zu `mcs.nn~`.
- **Status:** 🔲 geplant (Phase 6).

### `mab.info` (Model Inspection)
- Helper object that queries the model in the background and prints available methods, input/output dimensions, and attributes in the Max window (`dump`).
- Analog zu `nn.info`, aber **prozessisoliert** (kein libtorch im Max-Prozess): Worker läuft im `--query`-Modus und liefert Metadaten (Methoden, `channels_in/out`, Ratios, Attribute).
- **Status:** 🟢 FERTIG (Phase 4). Implementiert in `source/projects/mab_tilde/mab_info.cpp` + `worker_launch.cpp`. 1 Inlet, 5 Outlets (path/methods/attributes/parameters/dict). Messages: `set <path>`, `bang`/`dump`, `path`, `methods`, `attributes`, `parameters`, `dict`, `dump_dict`. Läuft mit eigenem, kurzlebigem Worker (`--query`-Modus, Exit 0), kein Audio-Ringbuffer nötig.

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

### 3.8 Real-Time Priority: Worker Must Never Starve the Audio Thread
- **Rule:** The inference worker must run at `BELOW_NORMAL_PRIORITY_CLASS` so the
  Max/ASIO audio thread always preempts it. The worker must never spread its
  inference threads across all cores (root cause of the nn_tilde ASIO buffer
  overflows under Windows).
- **Implementation (worker_launch.cpp):** After `CreateProcessW` call
  `SetPriorityClass(pi.hProcess, BELOW_NORMAL_PRIORITY_CLASS)` and
  `SetProcessAffinityMask(pi.hProcess, sysMask & ~1)` (all cores except core 0,
  guarded for single-core systems).
- **Implementation (inference_worker.py):** `cores` CLI argument (default 1)
  sets `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS` and
  `torch.set_num_threads(cores)` before the first model load.
- **CPU-only:** `cores` is honored only in CPU mode (`gpu 0`); inactive in GPU
  mode (CUDA does not use OpenMP/MKL threads), re-applied on switch back to CPU.
- **User control (mab~):** Optional 6th argument `[mab~ model method bufsize
  gpu #channels cores]`; `cores=1` is the RT-safe default.
- **Blocking for Phase 5/6:** `mc.mab~` and `mcs.mab~` may only use the shared
  `worker_launch` path and must inherit these priority/affinity/thread settings.

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
   cmake --preset debug
   cmake --build --preset debug
   ```
   (Ohne Presets: `cmake -B build -G "Visual Studio 18 2026" -A x64` +
   `cmake --build build --config Debug`)
3. **Result:** Compiled `mab~.mxe64` will be in `build/Debug/`

### 4.1 Deploy nach Max 9 (Max-Package) + Worker-Pfad-Auflösung

Zum Testen in Max wird das External in das Max-9-Package deployt. **Wichtig:**
Max muss geschlossen sein, sonst ist `mab~.mxe64` geladen/gesperrt (Fehler
"used by another process").

```powershell
# External kopieren (bei jedem Rebuild)
Copy-Item -Force build\Debug\mab~.mxe64 "$env:USERPROFILE\Documents\Max 9\Packages\mab_tilde\externals\"
# Worker-Skript (einmalig nach jeder Änderung an inference_worker.py)
Copy-Item -Force inference_worker.py "$env:USERPROFILE\Documents\Max 9\Packages\mab_tilde\support\"
# venv-Junction (einmalig; vermeidet GB-Kopie von torch)
New-Item -ItemType Junction -Path "$env:USERPROFILE\Documents\Max 9\Packages\mab_tilde\support\.venv" `
          -Target "$env:USERPROFILE\Documents\GitHub\artqcid\ai-projects\mab_tilde\.venv"
```

Package-Layout (Standard: `externals/` + `support/`):

```
Documents\Max 9\Packages\mab_tilde\
  externals\mab~.mxe64
  support\inference_worker.py
  support\.venv\          # Junction -> Projekt-.venv
```

**Worker-Pfad-Auflösung im C++ (nicht hartcodiert):** `resolve_worker_dir()`
in `mab_tilde.cpp` prüft zuerst die Env-Var `MAB_PROJECT_DIR` (optional, wenn
sie auf einen Ordner mit `inference_worker.py` zeigt), sonst steigt sie vom
DLL-Verzeichnis auf. Pro Ebene wird `<dir>\inference_worker.py` (Dev:
Repo-Root) **und** `<dir>\support\inference_worker.py` (Max-Package) geprüft.
Die venv-Python wird als `<project_dir>\.venv\Scripts\python.exe` (bevorzugt)
bzw. `venv\Scripts\python.exe` gesucht. Log-Ausgabe: `<project_dir>\mab_worker.log`.
Fehlersymptom "Timeout, kein Log, kein venv" = der Ordner mit
`inference_worker.py` wurde nicht gefunden → Pfad-Auflösung prüfen.

> **Wichtig:** Der Generator ist auf `"Visual Studio 18 2026" -A x64` gepinnt
> (`CMakePresets.json` + Guard in `CMakeLists.txt`). Wenn auf dem Rechner ein
> leerer/kaputter `C:\Program Files\Microsoft Visual Studio\2022`-Ordner liegt,
> wählt CMake sonst den defekten "Visual Studio 17 2022"-Generator als Default
> und bricht mit "could not find any instance of Visual Studio" ab.

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
- **could not find any instance of Visual Studio**: Generator-Default zeigt auf einen
  leeren VS-17-Ordner. Fix: `cmake --preset debug` (Generator in CMakePresets.json +
  CMakeLists-Guard gepinnt) oder `cmake -B build -G "Visual Studio 18 2026" -A x64`
- **undefined ext_main**: Verwende `__declspec(dllexport)` für MSVC, alle Callbacks in `extern "C"` Block
- **Objekt wird rot**: Dateiname muss `mab~.mxe64` heißen (OUTPUT_NAME "mab~" in CMakeLists.txt)
- **Crash in mab_tilde_new**: Verwende `long` statt `std::atomic<bool>` in C-Struct (object_alloc = malloc)

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

## 6. MCP Server & SQLite-RAG (Projektwissen für Cloud-Codierung)

Für Coding mit Cloud-Modellen (z.B. über OpenRouter) dient der lokale MCP-Server
`mab_mcp_server.py` als Wissensbrücke zum privaten Projektcode. Er wird über
`.mcp.json` automatisch von VS Code/opencode gestartet.

### 6.1 RAG-Tools (MCP)
- `index_project_code(directory_path)` – Indiziert alle Projektdateien
  (C++, Python, Markdown) rekursiv in die SQLite-FTS5-Datenbank `mab_rag.db`.
  Inkrementell (SHA-256), entfernte Dateien werden aufgeräumt.
- `query_code_rag(query, top_k)` – FTS5-Volltextsuche mit Trigramm-Tokenizer.
  Findet auch Identifikatoren wie `mab_tilde`, `block_size`, `dsp_setup`
  (Substring-Matching) und liefert Chunks mit Dateipfad + Zeilennummern.
- `inspect_rave_model(model_path)` – RAVE/ONNX/TorchScript-Analyse (Hop-Size,
  Ein-/Ausgangs-Shapes, `encode`/`decode`/`forward`).

Weitere Tools: `validate_ipc_sync`, `search_max_sdk_docs`, `inspect_model_metadata`,
`validate_rave_config`, `run_cpp_tests`, `get_project_info`, `analyze_inference_worker`.

### 6.2 Regeln für Coding-Agents
1. **Immer echten Quellcode verifizieren:** Antworten über das Projekt müssen
   aus den tatsächlichen Dateien stammen (`source/projects/mab_tilde/mab_tilde.cpp`,
   `inference_worker.py`). RAG-Treffer sind Einstiegspunkte, kein Ersatz für die
   Quelldateien.
2. **RAG nutzen:** Vor Implementierungen `query_code_rag` aufrufen, um exakte
   Signaturen, Konstanten (`CONTROL_RING_SIZE`, `MAX_BLOCK_SIZE`, `MAGIC_NUMBER`)
   und Message-Handler zu verifizieren.
3. **Index aktuell halten:** Nach Änderungen an `.cpp/.h/.py/.md` ggf.
   `index_project_code` erneut ausführen, damit die RAG-Datenbank nicht veraltet.
4. **Doku pflegen:** `WORKSPACE_AGENT_PROMPT.md` und `AGENTS.md` sind die zentrale
   Anleitung. Architektur-Änderungen müssen dort mitdokumentiert werden.

### 6.3 RAG-Datenbank
- `mab_rag.db` wird von `index_project_code` erzeugt (Laufzeit-Artefakt, in
  `.gitignore`). `Remove-Item mab_rag.db*` erzwingt einen vollständigen Neuaufbau.
- **Referenz-Repo nn_tilde:** lokaler Clone `C:\Users\marku\Documents\GitHub\thirdParty\nn_tilde`
  (Remote `acids-ircam/nn_tilde`). Dessen Kerndateien
  (`src/frontend/maxmsp/shared/nn_base.h`, `nn_tilde/nn_tilde.cpp`, `nn.info/nn.info.cpp`,
  `mc.nn_tilde/`, `mcs.nn_tilde/`, `shared/{array,buffer,dict}_tools.h`, `src/shared/*.h`,
  `src/source/*.py`) sind in denselben RAG-Index indiziert; `query_code_rag` findet sie.
  Vollständiger Parameter-Vergleich: `doc/nn_tilde_parity.md`.
- Ausgeschlossene Verzeichnisse (fremder Code/Rauschen): `max-sdk-base`,
  `min-api`, `min-lib`, `build`, `.venv`, `.git`, `__pycache__`, `node_modules`.
- Indizierte Formate: `.cpp/.h/.hpp/.cc/.cxx/.c`, `.py`, `.md`.

---

## 7. Required Deliverables

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

3. **`mab_mcp_server.py`** – MCP server with SQLite-RAG tools
   (`index_project_code`, `query_code_rag`, `inspect_rave_model`) plus
   Validierungs-/Analyse-Tools für Entwicklung und Agent-Support.

4. **`AGENTS.md`** – Agent-Instructions (auto-load von opencode/Continue),
   verweist auf diese Datei als zentrale Anleitung.

---

**End of Prompt**  
Use this file as the central guide for all coding agents working on the `mab_tilde` project. It defines the required functionality, architecture, and message contract for the MaxMSP external and its Python backend.