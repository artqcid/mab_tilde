# mab~ – Offene Tasks

_Stand: 2026-08-11. Nur offene Punkte, keine abgeschlossenen Tasks._
_Einlese-Reihenfolge: checklist.md → code_wiki.md → query_code_wiki → query_code_rag → get_rag_chunk_

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
  - Offen: `mab_tilde.cpp:310-333` – Arg-Parsing: `argv[3]=gpu`, `argv[4]=num_channels`, `argv[5]=cores` → muss mit nn_tilde-Reihenfolge (args[3]=inlets, args[4]=outlets) abgeglichen werden
  - Offen: `mab_tilde.cpp:256`/`1082` – `dsp_setup`/`outlet_new`: Inlet/Outlet-Count aus Overrides
  - Offen: `inference_worker.py:1209-1260` – argparse: positionale Args um `n_batches`/Overrides erweitern
  - Abhängig von Phase 5 (mc.mab~) / Phase 6 (mcs.mab~, `n_batches`)
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

### ❌ Offen

- [ ] **5.8** Max-Runtime-Verifikation: `[mc.mab~ musicnet.ts decode 2048]` mit `[noise~ 16]`
  - **Fix deployt (2026-08-11):** `Z_MC_INLETS | Z_NO_INPLACE`-Flags in `mc_mab_tilde_new` + `mab_tilde_rebuild_io` (`z_dsp.h:45`, min-api-Referenz `c74_min_operator_vector.h:120-128`) — ohne `Z_MC_INLETS` lieferte Max nur Kanal 1 an den Inlet
  - Erwartung: Max-Konsole zeigt `mc.mab~: DSP: 1 inlet(s), 16 channel(s) connected (model expects 16)`; alle 16 Latent-Kanäle wirken auf den Audio-Output
  - Deploy: `Copy-Item build\Debug\mc.mab~.mxe64 "$env:USERPROFILE\Documents\Max 9\Packages\mab_tilde\externals\"` (Max dafür schließen/neu starten)

## Phase 6 – mcs.mab~ (Batched Multichannel)

- [ ] **6.1** `n_batches` Inlets + Outlets, gemeinsame Kernlogik wie mc.mab~
  - `mab_tilde.cpp` + neues `mcs_mab_tilde.cpp` oder Template
- [ ] **6.2** `multichanneloutputs`/`inputchanged` mit Batch-Map
- [ ] **6.3** Shared Memory: `(n_batches × channels_in × block_size)`, Python: `view(n_batches, ci, bs)`
  - `inference_worker.py` (Inferenz-Loop Batch-Dim)
- [ ] **6.4** Verifikation: `[mcs.mab~ musicnet.ts encode 4 2048]` → 4 in, je 16 latent-out

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

