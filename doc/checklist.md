# mab~ – Offene Tasks

_Stand: 2026-08-11. Nur offene Punkte, keine abgeschlossenen Tasks._
_Einlese-Reihenfolge: checklist.md → code_wiki.md → query_code_wiki → query_code_rag → get_rag_chunk_

## Bugs

- [x] **Bug 1 – RAVE-Modelle (nasa, vintage) crashen Max mit Buffer-Overflow** ✅ **FIXED** (2026-08-11)
  - **Symptom:** `nasa.ts`, `vintage.ts` und aehnliche konvolutionelle RAVE-Modelle produzieren sofort NaN/Inf-Werte, die Max's Audio-Engine ueberlasten und zum Absturz bringen («bufferoverflow und knackser und dropouts»).
  - **Ursache:** `infer_method()` hatte keinen NaN/Inf-Guard und kein Output-Clipping. Die Modelle haben zwar interne `cached-conv`-Streaming-Buffer (mit `--streaming` exportiert), koennen aber trotzdem bei bestimmten Eingaben oder Zustandswechseln NaN-Werte erzeugen.
  - **Fix (inference_worker.py):**
    - `ConvStreamingContext`-Klasse (Z. 827–900): auto-detektiert konvolutionelle Modelle OHNE interne Streaming-Buffer (3D-Gewichte + `cache.pad`/`pad`-Buffernamen). Nur dann aktiv, wenn das Modell Conv-Layer hat, aber KEINE cached-conv-Buffer — bei `nasa`/`vintage`/`musicnet` derzeit `active=False`.
    - NaN/Inf-Guard in `infer_method()`: `torch.where(torch.isfinite(out), out, torch.zeros_like(out))` — immer aktiv.
    - Optionales Hard-Clipping: `safety_clip=True` → `torch.clamp(out, -1.0, 1.0)` — im Main-Loop aktiv, in Tests deaktiviert.
    - Streaming-Reset bei `method`-Wechsel und `enable 1`.
    - `_load_and_configure` erzeugt/ersetzt `ConvStreamingContext` bei jedem Modell-Load/Reload.

- [x] **Bug 2 – Worker startet nicht nach Deploy (Arg-Mismatch C++ ↔ Python)** ✅ **FIXED** (2026-08-11)
  - **Symptom:** Nach Build+Deploy startet der Python-Worker nicht. `mab_worker.log` bleibt leer. `mab.info dump` funktioniert, `mab~` nicht. "no such object" nach Max-Neustart. GPU-Modus zeigt kein geladenes Modell.
  - **Ursache (Teil 1 – Arg-Mismatch):** Die C++-Seite uebergibt seit Phase 6 ein `n_batches`-Argument an Position 5 (`mab_tilde.cpp:777`), aber die deployte `inference_worker.py` im Max-Package (`support\`) war veraltet und kannte das `n_batches`-Arg nicht. Der Parser interpretierte `n_batches=1` als `shm_name` → `invalid int value` → crash vor erstem `print()`.
  - **Ursache (Teil 2 – GPU/Venv):** `find_worker_dir` findet `inference_worker.py` im Max-Package (`support\`), aber das `.venv` mit CUDA-torch liegt im Git-Projekt. Ohne Venv fiel der Worker auf System-Python `C:\Python314\python.exe` zurueck — hat `torch 2.10.0+cpu`, kein CUDA.
  - **Ursache (Teil 3 – Falscher Ordner):** `deploy.ps1` kopierte nach `Max9` (ohne Leerzeichen). Max 9 lädt Externals aus `Max 9` (mit Leerzeichen).
  - **Fix:**
    - `inference_worker.py` muss bei jedem Deploy mit kopiert werden (neben `.mxe64`).
    - Deploy-Script `deploy.ps1` erstellt (build + copy `.mxe64` + `inference_worker.py`).
    - `worker_find_venv_python`: sucht `.venv` rekursiv aufwaerts (nicht nur im project_dir).
    - `deploy.ps1`: erstellt `.venv`-Junction im Max-Package + setzt `MAB_PROJECT_DIR` env var.
    - VSCode-Task `Deploy to Max 9` in `.vscode/tasks.json`.
    - In `AGENTS.md` und `projektwissen.md` dokumentiert.

## Feature Requests

- [x] **FR1 – Timer-Resolution + Python-Thread-Priorität (ASIO XRun-Prävention Stufe 1)** ✅ **DONE** (2026-08-11)
  - **Ziel:** Reduziert Wake-up-Jitter des Python-Workers von ~16 ms auf ~1 ms und stellt sicher, dass der Audio-Thread auch innerhalb des `BELOW_NORMAL`-Prozesses präemptieren kann.
  - **Maßnahmen:**
    1. `timeBeginPeriod(1)` in `_init_xrun_prevention()` (`inference_worker.py:1378-1395`) → Windows-Timer-Resolution von 15.6 ms auf 1 ms
    2. `SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_LOWEST)` in `_init_xrun_prevention()` → Python-Haupt-Thread priorisiert den Audio-Thread
  - **Dateien:** `inference_worker.py:1378-1395` (`_init_xrun_prevention`), `inference_worker.py:1467` (Aufruf in `main()`)
  - **Test:** Alle 19 C++-Tests ✅, alle Python-Tests ✅; XRun-Verifikation in Max (manuel)

- [ ] **FR2 – Triple-Buffering (ASIO XRun-Prävention Stufe 2)**
  - **Ziel:** Bei langsamer Inferenz hat C++ immer einen fertigen Output-Buffer als Reserve, statt auf den einzigen zu warten.
  - **Maßnahmen:** 3 Output-Buffer statt 2 in `SharedMemoryManager` → Header-Feld `n_buffers` (2 oder 3), `input_buffer_index`/`output_buffer_index` modulo `n_buffers`.
  - **Dateien:** `inference_worker.py:122-160` (SharedMemoryManager), `mab_tilde.cpp:56-67` (SharedMemoryHeader), `mab_tilde.cpp:607-647` (perform64)
  - **Kosten:** +50% Output-SHM (z.B. +32 KB für mono 2048, vernachlässigbar)

- [ ] **FR3 – Memory-Allocator-Stabilisierung (ASIO XRun-Prävention Stufe 2)**
  - **Ziel:** Verhindert CPU-Spikes durch PyTorch-Auto-Tuning und Allocator-Jitter.
  - **Maßnahmen:**
    1. `torch.backends.cudnn.benchmark = False` → deterministisch, kein Auto-Tuning beim ersten Forward
    2. `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` (GPU) → weniger Fragmentierung
    3. `os.environ['OMP_WAIT_POLICY'] = 'PASSIVE'` → OpenMP-Threads verbrauchen weniger CPU im Leerlauf
  - **Dateien:** `inference_worker.py:1341-1358`, `load_model()`
  - **Achtung:** `cudnn.benchmark=False` kann GPU-Inferenz verlangsamen — nur wenn nötig aktivieren

## Feature Requests (offen)

(siehe oben)

## Bugs (offen)

- [x] **Bug 3 – GPU-Argument beim Konstruktor ignoriert** ✅ **FIXED** (2026-08-12)
  - **Symptom:** `mab~ nasa 2048 1` laedt nicht auf GPU. Der User muss erst `gpu 1` als Message senden.
  - **Ursache:** Die Argument-Reihenfolge `[model method bufsize gpu]` macht `method` zum Pflichtargument. Bei `mab~ nasa 2048 1` wird `2048` als `method_name` und `1` als `buffer_size` geparst — `gpu` bleibt 0.
  - **Fix:** Auto-Detection in `mab_tilde_new`/`mc_mab_tilde_new`/`mcs_mab_tilde_new`: wenn `argv[1]` ein Symbol ist → `[model method bufsize ...]`; wenn es eine Zahl ist → `[model bufsize ...]` (method entfaellt, defaultet auf `forward`).
  - **Dateien:** `mab_tilde.cpp:380-400` (mab_tilde_new), `mab_tilde.cpp:1231-1256` (mc_mab_tilde_new), `mab_tilde.cpp:1564-1599` (mcs_mab_tilde_new)

- [x] **Bug 4 – forward/decode: kein Ton + Crash (nasa, GPU)** ✅ **FIXED** (2026-08-12)
  - **Symptom:** `mab~ nasa decode 2048 1` produziert keinen Ton. `mab~ nasa forward 2048 1` crashed Max bei Signal-Eingang. Python-Worker bleibt am Leben.
  - **Modell-Params (nasa):** `decode=(8,2048,1,1)`, `encode=(1,1,8,2048)`, `forward=(1,1,1,1)`, `prior=(1,2048,8,2048)`.
  - **Ursache decode:** `infer_method()`: `tensor[:, -1]` auf Shape `(1,8,2048)` selektierte Kanal 7 (2048 Samples), nicht letztes Zeit-Sample. `model.decode()` bekam `(1,1,2048,1)` statt `(1,8,1)` → RuntimeError → try/except → Output genullt → Stille.
  - **Ursache forward:** `forward_params=(1,1,1,1)` → Python produziert korrektes Audio. Crash war C++: `apply_io` rief `mab_tilde_rebuild_io(1,1)` obwohl Konstruktor bereits 1-in-1-out eingerichtet hatte. `object_free`/`outlet_new` auf selber Outlet-Position → DSP-Referenz korrumpiert → `bad object`.
  - **Fix decode:** `tensor[..., -1:]` ersetzt `tensor[:, -1]` → korrektes Shape `(B, ci, 1)`.
  - **Fix forward:** `apply_io` tracked `last_io_in`/`last_io_out` — skipped `mab_tilde_rebuild_io` wenn IO unverändert.
  - **Dateien:** `inference_worker.py:952-956` (decode Fix), `mab_tilde.cpp:749-763` (apply_io Skip)

- [x] **Bug 5 – GPU-Nachricht + Init-Race (bad object)** ✅ **FIXED** (2026-08-12)
  - **Symptom 1:** `gpu 1` Message während Audio läuft → `object_class_internal: bad object` ×4 → Max crasht.
  - **Symptom 2:** `mab~ nasa decode 2048 1` (GPU-Direktstart) → gleicher Fehler.
  - **Ursache 1:** `mab_tilde_gpu` startete async GPU-Reload ohne bypass. Python schrieb `method_id`/`channels_in/out` ins SHM während `perform64` parallel lief → Buffer-Stride-Mismatch → DSP-Korruption.
  - **Ursache 2:** `init_worker` setzte `is_ready=1` VOR `method_pending=1+qelem_set`. `perform64` konnte in diesem Fenster mit `is_ready=1` aber veralteten `x->channels_in/out` feuern.
  - **Fix 1:** `gpu`-Handler setzt `is_bypass=1` + `active_method_id=0` + `clock_fdelay(gpu_reload_clock, 3s)`. Clock-Callback cleared bypass nach Reload. `apply_io` cleared bypass nach IO-Rebuild.
  - **Fix 2:** `is_ready=1` erst NACH `method_pending=1+qelem_set` → kein Race-Fenster.
  - **Dateien:** `mab_tilde.cpp:911-948` (gpu-Handler), `mab_tilde.cpp:845-853` (init_worker Reihenfolge)

---

## Max-Runtime-Verifikation

- [ ] **V1 – decode-Layout** `[mab~ musicnet.ts decode 2048]` → 16 latent in, 1 audio out, keine dropouts
  - `mab_tilde.cpp:511-596`, `inference_worker.py:1516-1555`
  - Hängt von: Build + Deploy nach Max
- [ ] **V2 – forward** `[mab~ musicnet.ts forward]` → 1 in/1 out
  - Gleiche Dateien
- [ ] **V3 – encode** `[mab~ musicnet.ts encode]` → 1 audio in, 16 latent out
  - Gleiche Dateien
- [ ] **V4 – Methodenwechsel** `method decode`/`method encode` zur Laufzeit
  - `mab_tilde.cpp:1008-1021` (mab_tilde_method)
- [ ] **V5 – mab.info** `[mab.info musicnet.ts]` → `bang` listet Methods/Attributes/Params
  - `mab_info.cpp:57-113`, `inference_worker.py:686-774` (collect_model_info/print_info_block/query_model)
- [ ] **V6 – void-Mode** `[mab~ void 4 2]` → 4 inlets, 2 outlets, kein Worker
  - `mab_tilde.cpp:252-375` (mab_tilde_new)

## Parity-Luecken (nn_tilde)

- [ ] **P7 – track_buffers + buffer~-Support**
  - Vorbereitung ✅: `source/projects/mab_tilde/buffer_manager.h` (BufferRef/BufferManager/`buffer_manager_init`), Feld `buffer_mgr` in `t_mab_tilde` (`mab_tilde.cpp:68-125`), Kommentar-Block in `inference_worker.py` (P7-API)
  - Offen: `buffer_reference`-Anbindung (nativer Max-SDK) + Max-Runtime-Test
- [ ] **P10 – Argument-Overrides** (Arg4/5 Inlet-/Outlet-Anzahl, mcs `n_batches`)
  - Dokumentation ✅: `doc/nn_tilde_parity.md` §3 (nn_tilde: `nn_base.h:419-478`, `mcs.nn_tilde.cpp:189-259`)
  - Teilweise ✅: `t_mab_tilde` Feld `n_batches` + `channel_map` existiert (`mab_tilde.cpp:124-125`), Void-Mode-Clamping (`mab_tilde.cpp:339-348`, `mc_mab_tilde_new:1136-1145`)
  - ✅ Phase 6: mcs `n_batches`-Arg implementiert (`mcs_mab_tilde_new`: `argv[2]=n_batches`), argparse um `n_batches` erweitert (`inference_worker.py:1219-1221`)
  - Offen: `mab_tilde.cpp:310-333` – Arg-Parsing mab~/mc.mab~: `argv[3]=gpu`, `argv[4]=num_channels`, `argv[5]=cores` → muss mit nn_tilde-Reihenfolge (args[3]=inlets, args[4]=outlets) abgeglichen werden
  - Offen: `mab_tilde.cpp:256`/`1082` – `dsp_setup`/`outlet_new`: Inlet/Outlet-Count aus Overrides (nur mab~/mc.mab~)
- [ ] **P11 – mab.info: download/delete-Messages** durchleiten
  - ✅ FERTIG: C++ Message-Handler `mab_info_download`/`mab_info_delete`/`mab_info_print` (`mab_info.cpp`), Worker-CLI-Flags `--download/--delete/--list` (`inference_worker.py`), Ergebnis auf Outlet 1, `object_error` bei Netzwerkfehlern
  - Offen: Max-Runtime-Verifikation (V5-Erweiterung)

## Phase 5 – mc.mab~ (Multichannel)

### ✅ Abgeschlossen

- [x] **5.1** Klassen-Registrierung `mc.mab~` — Doppelkompilierung per `#ifdef MC_MAB_TILDE_MODULE`:
  - `mab~.mxe64`: registriert nur `mab~`-Klasse
  - `mc.mab~.mxe64` (mit `MC_MAB_TILDE_MODULE`): registriert nur `mc.mab~`-Klasse
  - Shared-Struct `t_mab_tilde` (`mab_tilde.cpp:62-113`) mit `is_mc`, `channel_map[16]`, `n_batches`
  - `mc_mab_tilde_new`, `mc_mab_tilde_dsp64`, `mc_mab_tilde_perform64` implementiert
  - `mab_tilde_rebuild_io` als Shared Helper (erzeugt `"multichannelsignal"`-Outlets wenn `is_mc==1`)
  - `mab_tilde_apply_io` an `mab_tilde_rebuild_io` delegiert

- [x] **5.2** `multichanneloutputs` + `inputchanged` → `channel_map`:
  - `mc_multichanneloutputs(x, index, count)` → `n_batches` oder `channels_out`
  - `mc_inputchanged(x, index, count)` → `channel_map[index]=count`, publiziert in Header

- [x] **5.4** `chans <n>`-Attribut (fixe Output-Channel-Anzahl):
  - `mc_mab_tilde_chans` setter, speichert in `n_batches` (0 = auto)

- [x] **5.3** Shared Memory: Header **v3** mit `channel_map[16]`:
  - Header-Layout: 9×uint32(36) + method[52] + method_id(4) + 3×uint32(12) + 2×uint32(8) + `channel_map[16]`(64) + 4×long(16) = **192 Bytes** (static_assert in `mab_tilde.cpp:62-63`)
  - C++-Seite: `mc_mab_tilde_dsp64` liest `count[]` → `channel_map`, publiziert in Header; `mc_inputchanged` aktualisiert zur Laufzeit; `init_worker` initialisiert auf 0
  - Python-Seite: `SharedMemoryHeader`-ctypes + `read_channel_map()`/`get_total_input_channels()` (`inference_worker.py:346-373`); Inferenz-Loop nutzt Kanalzahl für Pass-through + MC-Wiring-Validierung
  - Fix: `mc_mab_tilde_dsp64` überschreibt `x->channels_in` nicht mehr (behebt Rebuild-Loop bei Abweichung verbundene↔deklarierte Kanäle)

- [x] **5.5** Latent + Multichannel kombiniert:
  - MC-IO ist immer **1-in-1-out** (Multichannel); Kanalzahl über `multichanneloutputs`/`channel_map` (`mab_tilde_apply_io`, `mab_tilde.cpp:650-665`)
  - decode → 1 mc-latent-inlet (16ch via `[noise~ 16]`) → 1 audio-mc-outlet
  - Zero-Padding: fehlende verbundene Kanäle (numins < deklariertem `channels_in`) werden von `block_accumulate_write` stillgelegt
  - Zero-Fill: Outlets über dem Modell-`channels_out` (z.B. `chans` > co) werden in `mc_mab_tilde_perform64` gesilenced
  - Test: `test/test_mc_mab_tilde.cpp` (7 Fälle: 1-in-1-out, chans, inputchanged, Zero-Padding, decode-Roundtrip)

- [x] **5.6** CMake: `mc.mab~`-MODULE-Target:
  - `CMakeLists.txt`: `add_library(mc_mab_tilde MODULE ...)` + `target_compile_definitions(... PRIVATE MC_MAB_TILDE_MODULE)` + `set_target_properties(... OUTPUT_NAME "mc.mab~" SUFFIX ".mxe64")`

- [x] **5.7** Build + Kompilierung:
  - `cmake --preset debug && cmake --build --preset debug` → `build/Debug/mc.mab~.mxe64`
  - Alle C++-Tests (18 EXEs inkl. `test_mc_mab_tilde`) grün, alle Python-Tests (119) grün

- [x] **5.8** Max-Runtime-Verifikation: `[mc.mab~ musicnet.ts decode 2048]` mit `[noise~ 16]` — **BESTANDEN (2026-08-11)**
  - Fix: `Z_MC_INLETS | Z_NO_INPLACE`-Flags in `mc_mab_tilde_new` + `mab_tilde_rebuild_io` (`z_dsp.h:45`, min-api-Referenz `c74_min_operator_vector.h:120-128`) — ohne `Z_MC_INLETS` lieferte Max nur Kanal 1 an den Inlet
  - In Max verifiziert: alle 16 Latent-Kanäle wirken auf den Audio-Output, Diagnose-`post()` bestätigt die verbundenen Kanäle
  - **Phase 5 damit abgeschlossen ✅**

## Phase 6 – mcs.mab~ (Batched Multichannel)

### ✅ Implementiert (2026-08-11)

- [x] **6.0** Analyse + Design-Entscheidungen festgelegt (noch kein Code):
  - Referenz `mcs.nn_tilde.cpp` (494 Z.) studiert: `n_batches`-Multichannel-Inlets/-Outlets, `channel_map` der Größe `n_batches` (Default alle 1), `get_batches()` = max(channel_map), Arg-Reihenfolge `[model, method, n_batches, bufsize]`, `multichanneloutputs` → `m_out_channels` pro Outlet-Index, `inputchanged` → `channel_map[index]` + Warnung bei Mismatch
  - **Doppelkompilierung wie Phase 5:** `MCS_MAB_TILDE_MODULE` in `mab_tilde.cpp` → `mcs.mab~.mxe64` (konsistent mit `MC_MAB_TILDE_MODULE`), kein separates Template nötig
  - **SHM-Layout (6.3):** batch-major `[n_batches × channels_in × block_size]` – C++ schreibt Zeile `b*ci + c`, Python `view(n_batches, ci, bs)`; weicht bewusst von nn_tildes interleaved `c*B + b` ab (checklist-Vorgabe)
  - **Header:** v3-`channel_map[16]` wird wiederverwendet (max. 16 Batches), 192-Byte-static_assert bleibt unverändert – kein Header-Bump nötig
  - **CMake:** `mc_mab_tilde`-Target (CMakeLists.txt:79-104) als Muster für `mcs_mab_tilde`-Target
  - Python-`infer_method` (inference_worker.py:793-838) muss für Batch-Dim erweitert werden (Batched-Forward `[n_batches, ci, bs]` statt `[1, ci, bs]`)
  - Unit-Test-Muster: `test/test_mc_mab_tilde.cpp` (logik-reine Spiegel ohne Max-SDK-Link)

- [x] **6.1** `n_batches` Inlets + Outlets, gemeinsame Kernlogik wie mc.mab~ — **FERTIG**:
  - `t_mab_tilde` um `is_mcs` + `mcs_batches` erweitert (neben `is_mc`/`channel_map`/`n_batches`); `mab_tilde_prefix()`-Helper für korrekte post-Prefixe
  - `ext_main` dreifach-kompiliert: `MCS_MAB_TILDE_MODULE` → registriert nur `mcs.mab~`-Klasse
  - `mcs_mab_tilde_new/dsp64/perf64` implementiert; Arg-Reihenfolge `[model method n_batches bufsize gpu cores]` (nn_tilde-Parität P9)
  - `mab_tilde_apply_io`: mcs → `mcs_batches` Inlets UND Outlets (Multichannel); `mab_tilde_rebuild_io` erzeugt `"multichannelsignal"`-Outlets (is_mc=1)
  - `init_worker`-argbuf um `n_batches` erweitert (mab~/mc.mab~ senden 1)

- [x] **6.2** `multichanneloutputs`/`inputchanged` mit Batch-Map — **FERTIG**:
  - `mcs_multichanneloutputs`: `chans` (n_batches) gewinnt, sonst `channels_out` – pro Outlet-Index (wie mc.mab~)
  - `mcs_inputchanged`: `channel_map[index]` + Header-Publish + Warnung bei `count != channels_in` (nn_tilde-Parität P9)
  - `mc_mab_tilde_chans` prefix-neutral gemacht (wird von mc + mcs geteilt)

- [x] **6.3** Shared Memory batch-major + Python — **FERTIG**:
  - C++-perf64: flat `ins[]` → SHM-Zeilen `b*ci+c` (Null-Zero-Padding fehlender Kanäle), Drain `b*co+c` → Batch-Outlets bei `b*per_outlet+c`; überzählige Outlets gesilenced
  - `inference_worker.py`: `SharedMemoryManager(n_batches=...)`, Buffer `n_batches × ci × block_size`, `get_numpy_input/output` liefern 3D-Views `(B, ci, bs)`; `infer_method` batch-fähig (`(B,ci,bs)` → batched Forward → `(B,co,bs)`, 2D bleibt unverändert); argparse um `n_batches` erweitert; Wiring-Validierung gegen `ci * n_batches`; Passthrough per Batch
  - Header v3 unverändert (192 Bytes, `channel_map[16]` = Batch-Map, max. 16 Batches)

- [x] **6.4** Verifikation (Build + Unit-Tests) — **FERTIG**:
  - Unit-Test `test/test_mcs_mab_tilde.cpp` (8 Fälle: IO `n_batches`-in/out, Batch-Wiring batch-major, Partial-Batch-Zero-Padding, Output-Wiring + chans-Silencing, multichanneloutputs, inputchanged)
  - Python-Tests: `TestInferMethodBatched` (5 Fälle: forward/encode/decode/prior batched + Trim)
  - Build: `mcs.mab~.mxe64` (812 544 B) neben `mab~`/`mc.mab~`; alle 19 C++-Tests + alle 124 Python-Tests grün
  - **Offen: Max-Runtime-Test** `[mcs.mab~ musicnet.ts encode 4 2048]` → 4 in, je 16 latent-out (wie Phase 5.8, benötigt Max mit dem Modell)

## RAG/MCP-Verbesserungen

### Abgeschlossen (implementiert in Schritt 1–6 von rag_improvements.md)

- [x] **R1b** MCP-Tools: `search_max_sdk_docs` + `validate_ipc_sync` entfernt ✅, `run_cpp_tests` auf Presets + .exe-Ausführung umgestellt
  - `mab_mcp_server.py:913-954`
- [x] **R4** Kurze Queries: LIKE-Fallback in `_build_match_expr` + `_query_like_fallback`
  - `mab_mcp_server.py:607-695`
- [x] **R9** `.ragignore` erstellt + Filter in `_scan_directory`
  - `.ragignore`, `mab_mcp_server.py:463-502`
- [x] **R2** C++-Chunker: 3 Ebenen (namespace→class→method) – rekursiv implementiert
  - `mab_mcp_server.py:340-374` (_chunk_cpp_region), Test: `test_cpp_three_level_chunking`
- [x] **R11** Doc-Struktur bereinigt: `doc/checklist.md` extrahiert, `mab_dev_architecture.md` gestrafft
  - `doc/checklist.md` (73 Z.), `doc/mab_dev_architecture.md` (135 Z.)
- [x] **R10** Wiki-First-Workflow in `AGENTS.md` + `WORKSPACE_AGENT_PROMPT.md` verankert
- [x] **R8a** Compaction in `opencode.json`: `auto=true, keep=15000, buffer=20000`
- [x] **R8b** `max_steps`: plan=120, build=60, DEV=60, explore=24, general=12
- [x] **R8c** Plan-Agent permissions: bash+task+external_directory entfernt
- [x] **R8d** `AGENTS.md` (38 Z.) + `WORKSPACE_AGENT_PROMPT.md` (100 Z.) – kompakt genug ✅
- [x] **R14** MCP-Registrierung in `opencode.json` (statt `.mcp.json`): opencode lädt `.mcp.json` (Claude-Code-/VS-Code-Format) NICHT — `opencode mcp list` zeigte nur die 3 globalen Server
  - Fix: `mcp.mab-rave-assistant` in `opencode.json` (type=local, venv-python absolut, cwd=Projektroot, `PYTHONUNBUFFERED=1`)
  - Verifiziert: `opencode mcp list` → `mab-rave-assistant ✓ connected` (4 Server)
  - MCP-Tools erscheinen mit Server-Präfix `mab-rave-assistant_*`
  - Docs aktualisiert: `MCP_README.md`, `doc/projektwissen.md`, `WORKSPACE_AGENT_PROMPT.md`, `AGENTS.md`
  - Neustart von opencode erforderlich, damit die Tools in der laufenden Session verfügbar werden

### Offen (niedrige bis mittlere Priorität)

- [x] **R12** Wiki-Deduplizierung: `index_directory` canonicalisiert Pfade via `os.path.abspath()` (keine relativen Pfade mehr in der DB)
  - `mab_mcp_server.py:696` – `os.path.normpath` → `os.path.abspath(os.path.normpath(...))`
  - Zusätzlich Purge alter nicht-absoluter Einträge (`mab_mcp_server.py:706-716`)
  - Ergebnis: 44 statt 86 Dateien, 655 statt 1235 Symbole, Wiki von ~4000 auf ~2100 Zeilen
- [x] **R13** Wiki-Trennung: `generate_wiki` bettet `projektwissen.md` nicht mehr ein; stattdessen Referenz-Link
  - `mab_mcp_server.py:1088-1104` – `code_wiki.md` enthält nur den auto-generierten Symbolindex
  - Agents lesen `projektwissen.md` separat (keine 296-Zeilen-Duplikation mehr)

### Abgeschlossen (R5, R3, R6, R7 in diesem Durchlauf)

- [x] **R5** Stabile Chunk-IDs (Schema v4) – `chunk_id = hash(file_path + line_start + symbol_name)` — SHA-256 first 12 hex chars
  - `mab_mcp_server.py:102-110` (_stable_chunk_id)
- [x] **R3** Dependency-Graph im Code-Wiki: `used_by`-Beziehungen via Content-LIKE + Wort-Grenz-Prüfung
  - `mab_mcp_server.py:854-882` (_find_usages)
- [x] **R6** Wiki-Suche (`query_wiki`) auf FTS5 umgestellt; LIKE-Fallback für kurze Queries
  - `mab_mcp_server.py:732-770`
- [x] **R7** Semantic Search via Character-N-Gramm-Cosine-Reranking (keine externen Pakete)
  - `mab_mcp_server.py:118-168` (_char_ngrams, _ngram_embedding, _cosine_similarity, _semantic_rerank)
  - `query_code_rag(..., semantic=True)`

### Offene OpenCode-Konfiguration

- [x] **O1** `max_steps` in opencode.json: build=16 (belassen), explore=6, general=12 — ✅
- [x] **O2** Plan-Agent permissions: bash+task+external_directory entfernt — ✅
- [x] **O3** Compaction in opencode.json: auto=true, keep=15000, buffer=20000 — ✅ (bereits vorhanden)

---

_History: Diese Sektion konsolidiert den vollständigen Inhalt von `doc/rag_improvements.md` (gelöscht nach Übertragung). Siehe `doc/rag_improvements.md` (gelöscht) für den ursprünglichen Analyse- und Implementierungsplan._


## Offline-Tests (ohne Max Runtime) – siehe doc/test_strategy.md

### ✅ Abgeschlossen

- [x] **T0** Teststrategie-Dokument `doc/test_strategy.md` erstellt (Architect, 2026-08-11):
  - Analyse aller 20 Dateien (19 TorchScript-Modelle + 1 ONNX ausgeschlossen) in `D:\AI-Models\ts models`
  - 6 Test-Kategorien (A–F) definiert
  - Implementierungshinweise (subTest, GPU, Benchmark, CMake)
  - Geschätzter Aufwand: ~14-19 h

- [x] **T1 – Modell-Lade-Tests** `test/test_model_loading.py` (2026-08-11):
  - 18 TorchScript-Modelle auf CPU laden → `load_model()` + `eval()` (ONNX ausgeschlossen, `afterv2.audio.instr.ts` entfernt wegen RAM >10 GB)
  - 18 TorchScript-Modelle auf GPU laden (`skipIf(not torch.cuda.is_available())`, torch 2.12.0.dev+cu128 installiert)
  - `get_method_params()` + `compute_layout()` für jedes Modell
  - Dynamische Test-Generierung via `setattr()`: ein Test pro Modell (kein kumulativer Speicherdruck)
  - `torch.cuda.empty_cache()` nach jedem GPU-Test
  - Siehe `doc/test_strategy.md` §3 Kategorie B + §4.2

- [x] **T2 – mab.info-Integrationstests** `test/test_mab_info_models.py` (2026-08-11):
  - `query_model()` für jedes der 18 TorchScript-Modelle (ONNX ausgeschlossen)
  - stdout parsen → `MAB_INFO_BEGIN`/`MAB_INFO_END`, Modell-Typ, Methoden-Liste, Parameter
  - MABJSON-Block auf gültiges JSON validieren
  - Dynamische Test-Generierung via `setattr()`: ein Test pro Modell
  - CLI-End-to-End-Subprozess-Test gegen musicnet.ts
  - `query_model()` macht `del model` + `gc.collect()` vor `sys.exit(0)`
  - Siehe `doc/test_strategy.md` §3 Kategorie C

- [x] **T3 – Methoden-Dispatch-Integration** `test/test_infer_all_models.py` (2026-08-11):
  - `infer_method()` mit Zufalls-Input für jede Methode jedes Modells (18 Modelle)
  - Output-Shapes prüfen, NaN/Inf-Check
  - Dynamische Test-Generierung via `setattr()`: ein Test pro Modell mit `subTest()` pro Methode
  - Determinismus-Test nur für stateless Modelle (skip bei `encode`/`decode`, stateful RAVE)
  - `torch.set_num_threads(4)` gegen CPU-Überlastung/Thermal-Crash
  - RAM-Guard `_check_ram()`: skip wenn <2 GB frei
  - Debug-Logging via `logging.DEBUG` + Fortschritts-`print()` mit `flush()`
  - `afterv2.audio.instr.ts` entfernt (RAM-Verbrauch >10 GB beim Inferieren)
  - Siehe `doc/test_strategy.md` §3 Kategorie D

- [x] **T4 – Audio-Qualitätstests** `test/test_audio_quality.py` (2026-08-11, 49 Tests):
  - Forward-Passthrough: nur echte Audio-Effekt-Methoden (`effects.ts` thru/invert/add/polynomial/saturate) — RAVE-`forward` ist KEIN Passthrough (Autoencoder-Bottleneck, verifiziert: corr~0)
  - encode→decode Roundtrip: Streaming-Stabilität statt Rekonstruktion (nn_tilde-Semantik: decode liest nur letzten Latent-Frame → rekonstruktive Qualität nicht erwartbar)
  - Silence-Throughput: kein DC-Offset (Schwelle 0.2 — Voice-Modelle haben kleine DC-Reste)
  - Performance-Benchmark (ms pro Block, CPU, grosszuegiger Timeout)
  - `_test_signal()` = harmonisches Sinus-Signal (Zufallsrausch → NaN bei Voice-Modellen)
  - Siehe `doc/test_strategy.md` §3 Kategorie E

- [x] **T5 – Edge-Case-Tests** `test/test_model_edge_cases.py` (2026-08-11, 9 Tests):
  - Load/Unload-Cycles (10× musicnet.ts) — kein Leak/Crash
  - 2 Modelle nacheinander aktiv (musicnet+nasa, State-Isolation)
  - MAX_BLOCK_SIZE-Grenze (bufsize=4096)
  - Sehr kleine Blocks (bufsize=64, block_size bleibt >= 2048 wegen ratio)
  - Block-Grenzen (bufsize=0, bufsize=8192)
  - Unbekannte Methode → graceful exception
  - RAVE-Attribute set/get (demo_attributes.ts, RuntimeAttributes)
  - Null-Tensor-Input (kein Segfault)
  - Siehe `doc/test_strategy.md` §3 Kategorie F

- [x] **T6 – CMake-Test-Integration** `CMakeLists.txt` (2026-08-11):
  - `enable_testing()` + `add_test()` für alle 19 C++-Test-EXEs (TIMEOUT 180)
  - `add_test()` für 11 Python-Testdateien via `MAB_PYTHON` (venv-Auflösung, TIMEOUT 900)
  - `testPresets.debug` in `CMakePresets.json`
  - Verifiziert: `ctest --preset debug` → 19/19 C++ grün, Python-Tests registriert

- [x] **T7 – Benchmark-Report** `test/benchmark_models.py` (2026-08-11):
  - Performance-Datenblatt für alle 18 TorchScript-Modelle (ONNX: "nicht unterstützt", AFTER-v2: ausgelassen)
  - CPU vs GPU-Latenzen (RTX 3060) + GPU/CPU-Ratio
  - Markdown-Tabelle auf stdout (UTF-8)
  - GPU-Kompatibilitätsfehler (demo_mc/features) werden als "GPU-Fehler" vermerkt
  - Ergebnisse werden via `--report doc/benchmark_reports.md` als fortlaufend
    nummerierter **Testrun NNN – Datum** in `doc/benchmark_reports.md` eingetragen
    (neueste Messung oben, `--note` für Kontext)

