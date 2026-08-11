# Workspace Agent Prompt – mab_tilde

**Role:** Implement a crash-safe, process-isolated MaxMSP external replacing `nn_tilde` for TorchScript models (RAVE, AFTER) on Windows.

**Core design:** Python worker process + Windows shared memory (`MabSharedMem_{PID}`) + lock-free SPSC ring buffer. No libtorch in Max.

## 1. Objects

### `mab~`
- Args: `[mab~ model.ts (method) (buffer_size) (gpu) (num_channels) (cores)]`
- Default method: `forward`
- Method-aware IO via Header v2: `{method}_params = [channels_in, ratio_in, channels_out, ratio_out]`. IO rebuild via `mab_tilde_apply_io` on Max main thread (`t_qelem`).

### `mc.mab~` / `mcs.mab~`
- Phase 5/6. Not implemented yet.

### `mab.info`
- Process-isolated model inspector. 1 inlet, 5 outlets.
- Messages: `set`, `bang`/`dump`, `path`, `methods`, `attributes`, `parameters`, `dict`, `dump_dict`.

## 2. Messages

`enable [0/1]`, `gpu [0/1]`, `reload`, `dump`, `set <attr> <value...>`, `get <attr>`, `method <name>`, `load <path>`, `print_available_models`, `download <card>`, `delete <card>`.

## 3. Architecture rules

1. **Non-blocking startup.** `mab_tilde_new` never blocks Max main thread. Spawn worker in detached thread; object starts in bypass mode.
2. **`enable 0` / bypass / DSP off never kills the Python process.** PyTorch restart is too slow.
3. **Clean shutdown.** Destructor: send shutdown flag, wait max 500ms, force-kill if needed, unmap/close handles.
4. **Crash recovery.** Monitor worker handle. If worker dies, switch to bypass and print error. `reload` restarts worker.
5. **No OS locks in audio thread.** `perform64` uses only atomics / `Interlocked*`.
6. **Shared memory handshake.** Python creates SHM, loads model, writes Header v2, then signals ready. C++ attaches after signal.
7. **Memory layout.** Contiguous `[num_channels, block_size]` float arrays in SHM.
8. **RT priority.** Worker runs `BELOW_NORMAL_PRIORITY_CLASS` with affinity excluding core 0 (`worker_launch.cpp`). `cores` arg defaults to 1; sets `torch.set_num_threads`, `OMP/MKL/OPENBLAS_NUM_THREADS`. CPU-only; ignored in GPU mode.

## 4. Build

**Prerequisites:** VS Build Tools 2026 (VS 18), CMake 3.19+, Python 3.9+ with PyTorch.

Native Max SDK build (no min-devkit):
- Includes: `source/min-api/max-sdk-base/c74support/{max-includes,msp-includes}`
- Libs: `MaxAPI.lib`, `MaxAudio.lib`
- Output: `mab~.mxe64`

```powershell
Remove-Item -Recurse -Force build
cmake --preset debug
cmake --build --preset debug
```

**Deploy to Max 9 (Max closed):**
```powershell
Copy-Item build\Debug\mab~.mxe64 "$env:USERPROFILE\Documents\Max 9\Packages\mab_tilde\externals\"
Copy-Item inference_worker.py "$env:USERPROFILE\Documents\Max 9\Packages\mab_tilde\support\"
New-Item -ItemType Junction -Path "$env:USERPROFILE\Documents\Max 9\Packages\mab_tilde\support\.venv" `
          -Target "$env:USERPROFILE\Documents\GitHub\artqcid\ai-projects\mab_tilde\.venv"
```

Worker resolution (not hardcoded): `resolve_worker_dir()` checks `MAB_PROJECT_DIR`, then walks up from DLL path, looking for `inference_worker.py` and `support\inference_worker.py`.

**Troubleshooting:**
- Use `0L` not `CLASS_NOFLOAT`; `long` not `std::atomic<bool>` in C structs; `__declspec(dllexport)`; callbacks in `extern "C"`.
- Output name must be `mab~`.
- Pin generator: `"Visual Studio 18 2026" -A x64` via `CMakePresets.json`.

## 5. Python env

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 6. MCP / RAG

Local MCP server `mab_mcp_server.py` started via `.mcp.json`.

**Tools:** `index_project_code`, `query_code_rag`, `query_code_wiki`, `get_rag_chunk`, `inspect_rave_model`.

**MCP-First Workflow (verpflichtend, keine Ausnahmen):**
1. `doc/checklist.md` → naechsten offenen Task nehmen
2. `doc/projektwissen.md` → Struct-Layouts, Konstanten, Threading-Modell (manuell gepflegt, ~200 Zeilen)
3. `query_code_wiki("<symbol>")` → Signatur, Datei, Zeilennummer
4. **Nur wenn Wissen fehlt:** `query_code_rag(..., format="compact")`
5. **Nur benoetigten Chunk laden:** `get_rag_chunk("mab_XXX")`
6. Im echten Code verifizieren (path + line)
7. **Nach Aenderung:** `index_project_code` → Wiki wird aktualisiert

**MCP-PFLICHT (keine Ausnahmen):**
- `doc/code_wiki.md` DARF NIEMALS per `read()` geladen werden.
- JEDER Agent mit MCP-Zugriff MUSS `query_code_wiki` / `query_code_rag` / `get_rag_chunk` benutzen.
- Projekt- und SDK-Dateien nur mit `offset`/`limit` lesen — NIE ganze Dateien.
- Was einmal per MCP gefunden wurde, wird nie wieder gesucht.

**Post-Task Sync (nach jedem abgeschlossenen Task):**
- MCP nicht aktuell, Wiki aktuell: `index_project_code` → MCP nachziehen
- MCP nicht aktuell, Wiki nicht aktuell: `index_project_code` → beides aktualisieren
- Jeder Agent MUSS nach Code-Aenderungen `index_project_code` ausfuehren
- Falls nicht moeglich (kein MCP-Zugriff): explizit zurueckmelden dass Sync aussteht

`mab_rag.db` is runtime-only (`.gitignore`). `doc/projektwissen.md` is committed (manual knowledge).
`doc/code_wiki.md` is committed but NEVER read directly — use `query_code_wiki` via MCP.

## 7. Deliverables

- `source/projects/mab_tilde/mab_tilde.cpp`
- `inference_worker.py`
- `mab_mcp_server.py`
- `AGENTS.md` (this project's agent pointer)
- `doc/checklist.md` (offene Tasks)
- `doc/projektwissen.md` (manuelles Architekturwissen)