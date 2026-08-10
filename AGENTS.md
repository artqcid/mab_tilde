# AGENTS.md – mab_tilde Projekt

Diese Datei wird von opencode (und anderen Coding-Agents wie Continue)
automatisch geladen. Sie verweist auf die zentrale Anleitung und fasst die
wichtigsten Regeln des Projekts zusammen.

## Zentrale Anleitung

Lies **`WORKSPACE_AGENT_PROMPT.md`** vollständig, bevor du am Projekt arbeitest.
Sie definiert Architektur, Message-Contract und Build-Regeln des `mab~`-Externals.

## Projekt-Kurzüberblick

- Ziel: crash-sicheres, prozess-isoliertes MaxMSP-External `mab~` / `mc.mab~`
  als Ersatz für `nn_tilde` (TorchScript-Modelle wie RAVE, AFTER unter Windows).
  Geplant: `mab.info`, `mc.mab~` (echtes `mc.`), `mcs.mab~` – siehe `doc/implementation_plan.md`
  Phasen 4–6. Aktueller Stand: Phase 3 fertig (Method-Aware-Processing: Header v2,
  Latent-Inlets/Outlets via `mab_tilde_apply_io` auf dem Main-Thread, `block_accumulator`,
  `infer_method`-Dispatch) – nur Max-Verifikation offen (Task 3.4).
- Isolation: Python-Prozess + Shared Memory (`MabSharedMem_{PID}`),
  lock-free SPSC-Ringbuffer, Magic `0x4D414254` (`'MABT'`).
- Hauptcode: `source/projects/mab_tilde/mab_tilde.cpp` (C++) und
  `inference_worker.py` (Python/PyTorch).
- Build: CMake über `cmake --preset debug` + `cmake --build --preset debug`
  (Generator `"Visual Studio 18 2026" -A x64` ist in `CMakePresets.json` und per
  CMakeLists-Guard gepinnt), Ausgabe `build/Debug/mab~.mxe64`.
- Testen in Max: External + Worker-Skript ins Max-9-Package deployen (Max muss
  zu sein) – siehe WORKSPACE_AGENT_PROMPT.md §4.1 (`externals/` + `support/`
  mit `inference_worker.py` und `.venv`-Junction).

## Kernregeln (Architektur)

1. **Keine OS-Locks im Audio-Thread** (`dsp64`/`perform64`) – ausschließlich
   Atomics/`Interlocked*`, keine `WaitForSingleObject`/Mutexe.
2. **Asynchrone Initialisierung:** `new` blockiert nie den Max-Hauptthread;
   Objekt startet im Bypass-Modus und schaltet nach erfolgreichem Handshake um.
3. **`enable 0` / Bypass / DSP-Off beendet NIEMALS den Python-Prozess**
   (PyTorch-Neustart dauert Sekunden – State-Änderungen müssen sofortig sein).
4. **Clean Shutdown im Destruktor:** Shutdown-Flag senden, max. 500 ms warten,
   sonst Force-Kill des Prozesses, dann Shared-Memory-Handles schließen.
5. **Crash-Recovery:** Wenn der Python-Worker stirbt → Bypass-Modus + Fehler
   in der Max-Console, `reload` startet den Worker ohne Max-Neustart.
6. **Message-Contract:** `enable`, `gpu`, `reload`, `dump`, `set`, `get`,
   `method`, `load`, `anything` – siehe WORKSPACE_AGENT_PROMPT.md Abschnitt 2.
7. **Windows-MSVC-Notizen:** `long` statt `std::atomic<bool>` in C-Structs
   (object_alloc = malloc), `0L` statt `CLASS_NOFLOAT`, `__declspec(dllexport)`,
   Output-Name exakt `mab~` (`.mxe64`).
8. **Real-Time-Schutz des Audio-Threads (ASIO-XRun-Prävention):**
   - Worker-Prozess läuft IMMER mit `BELOW_NORMAL_PRIORITY_CLASS` + Affinität
     „alle Kerne außer Core 0“ (worker_launch.cpp) – der Audio-Thread präemptet
     den Worker garantiert.
   - Inferenz-Threads default `1` (kein All-Core-Spread): `cores`-Argument auf
     `mab~` (6. Position) → `torch.set_num_threads(cores)` +
     `OMP_NUM_THREADS`/`MKL_NUM_THREADS`/`OPENBLAS_NUM_THREADS`.
   - **CPU-only:** `cores` wirkt NUR im CPU-Modus (`gpu 0`); im GPU-Modus inaktiv
     (CUDA nutzt keine OpenMP/MKL-Threads). Re-Apply bei Wechsel zurück auf CPU.
   - Verpflichtend für Phase 5/6 (`mc.mab~`, `mcs.mab~`): nur gemeinsamer
     `worker_launch`-Pfad, Einstellungen erben.

## Projektwissen per RAG (MCP)

- Der MCP-Server `mab_mcp_server.py` läuft automatisch über `.mcp.json`.
- RAG-Tools: `index_project_code`, `query_code_rag`, `query_code_wiki`,
  `inspect_rave_model`.
- **Code-Wiki `doc/code_wiki.md`:** wird von `index_project_code` automatisch
  regeneriert (Symbolindex mit Pfaden + Zeilennummern, ~550 Symbole). Einmalig
  pro Session als stabilen Kontext lesen (prompt-cache-freundlich).
- Vor Code-Fragen das RAG abfragen, Antworten aber **immer an den echten
  Quelldateien** verifizieren (Pfade/Zeilennummern der Treffer nutzen).
- Nach Quellcode-Änderungen ggf. `index_project_code` erneut ausführen.

## Referenz-Code: nn_tilde (Paritäts-Quelle)

- Lokaler Clone: `C:\Users\marku\Documents\GitHub\thirdParty\nn_tilde`
  (Remote: `acids-ircam/nn_tilde`). **Hier** liegen die Original-C++-Sources von
  `nn~`/`mc.nn~`/`mcs.nn~`/`nn.info` (`src/frontend/maxmsp/`), die wir als
  Paritäts-Vorlage nutzen — NICHT im Max-9-Package (dort nur Python-Helpers).
- Kern-Dateien: `src/frontend/maxmsp/shared/nn_base.h`, `.../nn_tilde/nn_tilde.cpp`,
  `.../nn.info/nn.info.cpp`, `.../shared/buffer_tools.h`, `src/shared/model_download.h`,
  `src/source/*.py` (Demo-Modell-Attribute).
- Parameter-Vergleich + fehlende Optionen: `doc/nn_tilde_parity.md`.
- Die nn_tilde-Kerndateien sind zusätzlich im RAG-Index (`query_code_rag` findet
  `track_buffers`, `get_attributes`, `register_attribute`, `BufferManager`, ...).

## Subagent-Rechte (Autopilot)

- Explore-/General-Subagents arbeiten standardmäßig im **Autopilot-Modus**: Sie
  dürfen alle lesenden Werkzeuge (read/glob/grep), das RAG
  (`query_code_rag`/`index_project_code`), Web-Suche und projektbezogene
  `bash`-Kommandos (Tests, Linting) eigenständig und ohne Rückfrage nutzen.
- **Nur der Hauptagent** führt schreibende Operationen auf Quelldateien
  (edit/write), Git-Operationen sowie Build/Deploy aus – sofern nicht explizit
  anders beauftragt. Ergebnisse von Subagents müssen am echten Quellcode
  verifiziert werden.

## Doku-Pflicht

`WORKSPACE_AGENT_PROMPT.md` und diese Datei bei Architekturänderungen
mitpflegen. Keine neuen Verhaltensregeln nur im Chat, sondern auch hier ablegen.
