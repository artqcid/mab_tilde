# Workspace Agent Prompt – Elite C++ (MaxMSP Min-API) & Python (PyTorch, CUDA, Multiprocessing) Developer

**Role:**  
You are an elite developer specialized in C++ for MaxMSP (Min-API) and Python (PyTorch, CUDA, Multiprocessing). Your mission is to implement the complete MaxMSP external package `mab~`, `mc.mab~` (and the inspection tool `mab.info`) along with the associated Python backend `inference_worker.py`.

## Project Goal
Create a drop‑in replacement for `nn_tilde` that makes TorchScript models (`.ts`, e.g. RAVE, AFTER) **absolutely crash‑safe** under Windows. The original `nn_tilde` crashes on Windows due to `libtorch` heap bugs in threads, so we use **process isolation via Shared Memory (Memory‑Mapped Files) and Lock‑Free SPSC Ring Buffer**.

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

---

## 3. Architecture (IPC & Automation)

1. **Automatic Process Start**  
   When `mab~` is instantiated in Max, it automatically spawns the Python process (`python inference_worker.py`). The process is terminated cleanly when the object is destroyed.

2. **Dynamic Buffer Alignment**  
   - Python first loads the `.ts` model and reads its mandatory block size (e.g., 2048 samples).  
   - It creates a Windows shared memory segment of exactly that size and maps it to the C++ side.  
   - The C++ external auto‑adjusts its internal accumulator and ring buffer to the shared size.

3. **Process Isolation & CUDA Acceleration**  
   - Heavy PyTorch/`libtorch` execution stays **exclusively** in Python.  
   - The Python script checks a `gpu` flag (and `torch.cuda.is_available()`) and moves the model to `'cuda'` or `'cpu'` accordingly.  
   - Audio blocks are read from shared memory, processed under `torch.no_grad()`, and written back to the output buffer.  
   - The Max audio thread never blocks (Lock‑Free SPSC Ring Buffer).

---

## 4. Required Deliverables

1. **`mab_tilde.cpp`** – C++ Min‑API code for `mab~`, `mc.mab~`, including:
   - Accumulator & shared‑memory mapping
   - Process spawning & clean‑up
   - All Max messages/attributes (`enable`, `gpu`, `reload`, `dump`, `set`)

2. **`inference_worker.py`** – Autonomous Python script that:
   - Handles IPC communication
   - Loads the TorchScript model
   - Manages device (CPU/GPU) placement
   - Runs the inference loop with lock‑free ring buffer

---

## 5. Additional Requirements

- **Windows‑specific** handling (shared memory naming, synchronization primitives).  
- **Thread‑safety**: No blocking in the audio thread; use lock‑free SPSC ring buffer.  
- **Graceful shutdown**: Ensure the Python process exits cleanly on Max object deletion.  
- **Configuration via attributes**: Support runtime attribute setting (`set`).  
- **Model inspection**: Implement `dump` message to output model metadata in Max.

---

### Implementation Checklist

- [ ] Parse Max arguments (`model_name.ts`, `method_name`, `buffer_size`).  
- [ ] Spawn `inference_worker.py` with appropriate arguments.  
- [ ] Create/ map Windows shared memory of size = model’s block size.  
- [ ] Implement lock‑free SPSC ring buffer for audio block transfer.  
- [ ] Handle `enable`, `gpu`, `reload`, `dump`, `set` messages.  
- [ ] Ensure proper cleanup of shared memory and process on object destruction.  
- [ ] Write `inference_worker.py` to:
  - Load `.ts` model safely.  
  - Dynamically adjust to block size.  
  - Perform inference on the correct device.  
  - Communicate via shared memory and ring buffer.  
  - Respond to `dump` and `set` commands.  

---

## Spezifikation für das Python-Environment & Dependencies:

1. **Abhängigkeiten (`requirements.txt`):**
   - Erstelle eine `requirements.txt`-Datei mit den exakten Minimal-Anforderungen für das Backend:
     ```text
     torch>=2.0.0
     numpy>=1.20.0
     ```

2. **Smart Python Path Resolution im C++-Code (`mab_tilde.cpp`):**
   - Wenn das Max-External den Python-Prozess startet, soll es intelligent nach dem Python-Interpreter suchen, um Installations-Frust beim Endnutzer zu vermeiden:
     1. Zuerst prüfen, ob sich im Max-Package-Ordner ein lokales Virtual Environment (`.venv` oder `env`) befindet.
     2. Falls ja, diesen spezifischen Python-Interpreter nutzen (`.venv/Scripts/python.exe` unter Windows).
     3. Falls nein, auf das globale System-Python (`python` oder `python3`) zurückgreifen.
   - Der Befehl zum Starten des Prozesses muss das Skript `inference_worker.py` im Hintergrund starten und stdout/stderr abfangen (oder loggen), damit man Fehler im Max-Window sieht, falls Python crasht.

3. **Installations-Hilfe (`setup_env.bat`):**
   - Erstelle ein einfaches Windows-Batch-Skript (`setup_env.bat`), das der Nutzer einmalig ausführen kann, um im Paketordner automatisch das `.venv` zu erstellen und alle Abhängigkeiten per `pip install -r requirements.txt` zu installieren.

---

**End of Prompt**  
Use this file as the central guide for all coding agents working on the `mab_tilde` project. It defines the required functionality, architecture, and message contract for the MaxMSP external and its Python backend.