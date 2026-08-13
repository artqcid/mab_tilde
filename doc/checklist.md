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

- [ ] **FR3 – Memory-Allocator-Stabilisierung (ASIO XRun-Prävention Stufe 2)**
  - **Ziel:** Verhindert CPU-Spikes durch PyTorch-Auto-Tuning und Allocator-Jitter.
  - **Maßnahmen:**
    1. `torch.backends.cudnn.benchmark = False` → deterministisch, kein Auto-Tuning beim ersten Forward
    2. `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` (GPU) → weniger Fragmentierung
    3. `os.environ['OMP_WAIT_POLICY'] = 'PASSIVE'` → OpenMP-Threads verbrauchen weniger CPU im Leerlauf
  - **Dateien:** `inference_worker.py:1341-1358`, `load_model()`
  - **Achtung:** `cudnn.benchmark=False` kann GPU-Inferenz verlangsamen — nur wenn nötig aktivieren

- [x] **FR5 – Multiinstanz-Fähigkeit (encode+decode gleichzeitig, 2× forward)** ✅ **DONE** (2026-08-13)

  **Ziel:** Mehrere `mc.mab~`- / `mcs.mab~`-Objekte können gleichzeitig im selben Max-Patch laufen — auch mit gleichem Modell und verschiedenen Methoden (z.B. encode + decode) oder mit verschiedenen Modellen.

  **Root Cause:** `mab_tilde.cpp:552` — `instance_id = GetCurrentProcessId()`. Alle Objekte innerhalb desselben Max-Prozesses erhalten identische IDs → kollidierende Windows-Kernel-Objekte:

  | Kernel-Objekt | Name | Kollision |
  |---|---|---|
  | Named Event | `MabReadyEvent_{PID}` | `CreateEventW` öffnet dasselbe Event erneut |
  | Named Event | `MabInputReadyEvent_{PID}` | idem |
  | Shared Memory | `MabSharedMem_{PID}` | beide Worker schreiben in dasselbe Segment |

  `instance_id` wird außerdem nicht im `t_mab_tilde`-Struct gespeichert (nur lokal in `init_worker`).

  **Ansatz (nn_tilde-Parität):** 1 Max-Objekt = 1 Python-Worker = 1 SHM-Segment = 1 Satz Named Events. Kein Sharing zwischen Instanzen (nn_tilde lädt das Modell ebenfalls pro Objekt neu).

  **Empfohlene Lösung:** Objekt-Zeiger als Instance ID:
  ```c
  uint32_t instance_id = (uint32_t)((uintptr_t)x);
  ```
  Der Heap-Pointer ist pro Objekt garantiert eindeutig und für die gesamte Lebensdauer stabil. Keine neue Infrastruktur, keine Race Condition.

  **Änderungsumfang:**

  | Datei | Stelle | Änderung |
  |---|---|---|
  | `mab_tilde.cpp:552` | `init_worker` | `GetCurrentProcessId()` → `x->instance_id` |
  | `mab_tilde.cpp:76` | `t_mab_tilde` struct | `uint32_t instance_id;` hinzufügen |
  | `mab_tilde.cpp:~1055` | `mc_mab_tilde_new` | `x->instance_id` setzen, vor Thread-Start |
  | `mab_tilde.cpp:~1390` | `mcs_mab_tilde_new` | idem |
  | `inference_worker.py` | — | Keine Änderung nötig (nimmt `instance_id` bereits als Arg) |

  **Szenarien nach Fix:**

  | Szenario | Vorher | Nachher |
  |---|---|---|
  | 1× mc.mab~ forward | ✅ | ✅ |
  | encode + decode, gleiches Modell | ❌ SHM-Kollision | ✅ |
  | 2× forward, gleiche Modelle | ❌ SHM-Kollision | ✅ |
  | 2× forward, verschiedene Modelle | ❌ SHM-Kollision | ✅ |
  | mc.mab~ + mcs.mab~ gleichzeitig | ❌ SHM-Kollision | ✅ |

  **Tests:**
  - `test_instance_id_generation` (`test_init_worker_thread_comprehensive.cpp:383`) — Formel auf neuen Ansatz aktualisieren
  - Neuer Test: zwei `t_mab_tilde`-Stubs allozieren → assert `instance_id` verschieden, SHM-Namen verschieden
  - Python-Tests: keine Änderung nötig

  **Ressourcen:** 2 Objekte × 1 Modell = 2 Python-Worker = Modell 2× im RAM (nn_tilde-Parität, akzeptiert).
  Aufwand: ~1 h Implementierung + Tests.

  **✅ Umsetzung (2026-08-13):**
  - `t_mab_tilde.instance_id` (uint32_t) hinzugefügt (`mab_tilde.cpp:80`)
  - `init_worker`: `GetCurrentProcessId()` → `x->instance_id` (`mab_tilde.cpp:555`)
  - `mc_mab_tilde_new` (`:975`) + `mcs_mab_tilde_new` (`:1326`): `x->instance_id = (uint32_t)((uintptr_t)x)` vor Worker-Start
  - Test `test_instance_id_generation` auf Pointer-Ansatz umgestellt; zwei Allokationen → verschiedene IDs
  - Build + alle 22 C++-Test-EXEs grün, `test_python_shared_memory.py` 13/13 grün
  - **Offen:** Max-Runtime-Verifikation (2× mc.mab~ gleichzeitig im Patch) — kein Deploy durchgeführt

## Feature Requests (offen)

(siehe oben)

## Bugs (offen)

> **Aktueller Blocker: Bug 13** (`mab~` dynamischer Inlet-Rebuild → Crash + veraltete DSP-Chain). Blockiert V1/V3/V4.
> `mc.mab~` ist **nicht** betroffen (feste 1-MC-Inlet-Architektur, Phase 5.8 bestanden) und ist damit der funktionierende Pfad fuer Latent-Methoden.
> Bug 14 ist latent (nur bei non-streaming-Exporten).

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

- [x] **Bug 6 – mc.mab~: DSP erkennt nur 1 Kanal statt 8** ✅ **FIXED** (2026-08-12)
  - **Symptom:** `mc.mab~ nasa 2048 1` mit 8-Kanal-MC-Signal → Post `"DSP: 1 inlet(s), 1 channel(s) connected (model expects 8)"`. Nur Kanal 1 kommt durch.
  - **Ursache:** `mc_mab_tilde_dsp64` las Kanalzahl aus dem `count`-Array von `dsp64`. Der `count`-Array liefert bei MC-Inlets mit `Z_MC_INLETS` nicht zuverlässig die tatsächliche Kanalzahl (siehe nn_tilde, die stattdessen `inputchanged` nutzt). Zusätzlich überschrieb `dsp64` das von `inputchanged` korrekt gesetzte `channel_map`.
  - **Fix:** `mc_mab_tilde_dsp64`/`mcs_mab_tilde_dsp64` nutzen jetzt `channel_map` aus `inputchanged`-Callback als primäre Quelle. `count`-Array nur noch als Fallback wenn `inputchanged` noch nicht gefeuert hat.
  - **Dateien:** `mab_tilde.cpp:1351-1390` (mc dsp64), `mab_tilde.cpp:1673-1702` (mcs dsp64)

- [x] **Bug 7 – Worker-Zombie-Prozesse nach Max-Crash** ✅ **FIXED** (2026-08-12)
  - **Symptom:** Nach einem Max-Crash (Fenster schließt ohne Warnung) laufen Python-Worker-Prozesse weiter, halten GPU-Speicher und Shared-Memory-Handles. Bei Max-Neustart mit gleicher Process-ID → SHM-Namenskonflikt.
  - **Ursache:** Kein Mechanismus, der Worker-Prozesse automatisch beendet wenn der Elternprozess (Max) stirbt. `mab_tilde_free` läuft bei Crash nicht.
  - **Fix:** Windows Job Object mit `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. `init_worker` erstellt einen Job, weist den Worker-Prozess zu und speichert das Handle in `t_mab_tilde.worker_job_handle`. Beim Max-Exit/Crash schließt Windows das Handle → alle Worker im Job werden automatisch terminiert.
  - **Dateien:** `mab_tilde.cpp:78` (worker_job_handle Feld), `mab_tilde.cpp:855-864` (Job-Erstellung), `mab_tilde.cpp:499-504,601-606,1035-1038` (Cleanup)

- [x] **Bug 8 – Shutdown-Race: Worker-Timeout + Bypass-Flag** ✅ **FIXED** (2026-08-12)
  - **Symptom:** Max-Crash beim Wechsel von `mc.mab~` zu `mab~ nasa decode 2048 1` (Fenster schließt ohne Warnung). Ursächlich war GPU-Race: alter Worker hielt Modell auf GPU, wurde nach nur 500ms hart gekillt (`TerminateProcess`), neuer Worker startete und crashte die GPU bei Modell-Ladung.
  - **Ursache 1:** `mab_tilde_free`/`mab_tilde_reload` setzten `is_bypass=1, is_ready=0` NACH dem `UnmapViewOfFile` → `perform64` konnte während Cleanup auf freed SHM zugreifen.
  - **Ursache 2:** `WaitForSingleObject(python_process, 500)` → nur 500ms Timeout. Worker braucht länger für GPU-Modell-Entladung (`torch.cuda.empty_cache()`, Modell-Destruktor). `TerminateProcess` nach 500ms hinterlässt GPU-Allokationen.
  - **Fix 1:** `is_bypass=1, is_ready=0` als ERSTES in `mab_tilde_free`/`mab_tilde_reload` → perform64 sofort in Bypass.
  - **Fix 2:** Timeout 500ms → 5000ms (5s). Nach `TerminateProcess`: `Sleep(200)` für OS-GPU-Cleanup.
  - **Dateien:** `mab_tilde.cpp:459-464` (free bypass-first), `mab_tilde.cpp:488-497` (free 5s timeout), `mab_tilde.cpp:991-995` (reload bypass-first), `mab_tilde.cpp:1025-1030` (reload 5s timeout)

- [x] **Bug 9 – decode/prior: kein Ton bei mab~ (non-MC)** ✅ **FIXED** (2026-08-12)
  - **Symptom:** `mab~ nasa decode 2048 1` und `mc.mab~ nasa decode 2048 1` produzieren keinen Ton (Stille). `forward` funktioniert normal.
  - **Ursache:** `infer_method()` fügte die Batch-Dimension `unsqueeze(0)` nur im `else`-Zweig (forward/encode) ein, nicht im `decode`/`prior`-Zweig. Für 2D-Input `(8, 2048)` aus `get_numpy_input` ergab `tensor[..., -1:]` → `(8, 1)`. Das Modell interpretierte 8 als Batch-Größe (statt als Kanalzahl) → `model.decode((8, 1))` erwartete 8 separate 1-Kanal-Latents statt einem 8-Kanal-Latent → falsche/keine Audio-Ausgabe (`except`-Zweig nullte Output).
  - **Fix:** `tensor.unsqueeze(0)` VOR dem `decode`/`prior`-Zweig (einmalig nach `to(device)`), sodass `tensor` immer 3D `(B, ci, bs)` ist. `z = tensor[..., -1:]` ergibt dann korrekt `(1, 8, 1)`.
  - **Dateien:** `inference_worker.py:940-960`

- [~] **Bug 10 – Knackser: Output-Silence-Luecke pro Block-Zyklus** ⚠️ **TEILFIX, ERSETZT DURCH BUG 11**
  - **Symptom:** `mab~` und `mc.mab~` produzieren "total unbrauchbare Knackser" — Ausgabe stimmt NICHT mit nn_tilde ueberein, egal ob forward/decode/encode.
  - **Ursache (Teilbild):** Bei `is_output_ready == 0` gab C++ **Stille** aus statt Audio → 512-Sample-Luecke pro Blockzyklus (≈21.5 Hz Knackser bei 2048/512/44100).
  - **Umgesetzter Teilfix (2026-08-12):** Stille-Pfad in allen drei `perform64` durch Block-Looping ersetzt (`is_output_ready == 0` → aktuellen Block weiter/erneut lesen).
  - **Ergebnis:** Stille beseitigt, Knackser **bleiben**. Der Teilfix ist unzureichend und verschlimmert Defekt C aus Bug 11: bei Ankunft eines neuen Blocks steht `out_pos` an beliebiger Stelle → neuer Block wird ab der Mitte gelesen, sein Anfang nie → `out_pos` desynchronisiert dauerhaft von der Blockgrenze.
  - **Status:** Vollstaendige Ursachenanalyse und Loesung siehe **Bug 11**. Teilfix bleibt vorerst drin (besser als Stille), wird von Bug 11 ersetzt.
  - **Dateien:** `mab_tilde.cpp:677-696` (mab~), `1501-1526` (mc), `1849-1889` (mcs)

- [~] **Bug 11 – SHM-Pipeline: 3 Defekte verhindern kontinuierliches Audio** ⚠️ **IMPLEMENTIERT (2026-08-12), TEST OFFEN**
  - **Symptom:** Audio wird abgehackt ausgegeben, nicht kontinuierlich wie nn_tilde. Kein identisches Verhalten zur Referenz, egal welche Methode.
  - **Randbedingung:** nn_tildes In-Process-Ringbuffer + Compute-Thread ist **bewusst nicht** uebernommen (Speicherlecks unter Windows) — deshalb Python out-of-process. Die Loesung muss innerhalb der SHM-Architektur funktionieren.

  - **Defekt A – Input wird verworfen (Hauptursache)**
    - `mab_tilde.cpp:661` / `1488` / `1824`: `if (x->header->is_input_ready == 0) { ... }` — Gate ohne `else`.
    - Solange Python den Block nicht konsumiert hat (`is_input_ready == 1`), schreibt C++ **gar nichts**; die Samples des Ticks werden ersatzlos verworfen.
    - Verlustdauer pro Blockzyklus = Python-Latenz. Bei 12 ms Inferenz und 11.6 ms/Tick (512 @ 44.1 k): **~1 von 4 Ticks = 25 % des Eingangssignals verloren**. Bei `forward` baut das Modell auf einem zerhackten Eingang auf → zerhackter Ausgang.
    - Der Double-Buffer ist hier funktionslos: C++ schaltet `input_buffer_index` um, das Gate verhindert aber das Befuellen des zweiten Puffers — er liegt brach.
    - nn_tilde: `circular_buffer::put()` laeuft **jeden** Tick ungated, `full()` triggert nur die Inferenz. Kein Sample geht verloren.

  - **Defekt B – Python schreibt in den Puffer, den C++ gerade ausliest**
    - `inference_worker.py:1746-1747` dokumentiert es woertlich: `# C++ drains header.output_buffer_index; write into that same buffer.`
    - C++ inkrementiert `output_buffer_index` erst **nach** vollstaendigem Drain (`mab_tilde.cpp:690`). Waehrend der 46 ms Drain-Phase zeigt der Index auf den aktiven Puffer — genau dorthin schreibt Python.
    - Kein Ownership-Handshake: Python prueft `is_output_ready` vor dem Schreiben nicht. Ergebnis: halb alter / halb neuer Block innerhalb eines Drain-Zyklus → Sprung mitten im Block.

  - **Defekt C – Keine Latenz-Reserve, kein blockalignter Handover**
    - Zeitbudget bei 2048/512/44.1 k:
      ```
      T0..T3  Input Block N fuellen (46.4 ms)  ‖  Output Block N-1 drainen (46.4 ms)
      T3      Input N fertig → Python startet
      T4      Output N MUSS fertig sein   ← Slack = 0 ms
      ```
    - Der Output wird in genau dem Tick faellig, in dem Python erst anfaengt. Double Buffering erzeugt **keine** Reserve, nur paralleles Input-Fuellen.
    - nn_tilde hat strukturell einen ganzen Puffer Latenz (Drain laeuft hinter dem Write-Pointer her), mab_tilde hat null.
    - Zusaetzlich desynchronisiert der Bug-10-Teilfix `out_pos` von der Blockgrenze (siehe Bug 10).

  - **Loesungsplan – N-Block-Ring im SHM statt Ping-Pong**
    1. **Input-Ring, ungated** (N ≥ 4 Bloecke). Header bekommt `in_write_head` / `in_read_tail` als monoton steigende Zaehler. C++ schreibt **immer**, unabhaengig von Python. Overrun (Python zu langsam) verwirft den **aeltesten Block**, niemals den laufenden Tick. → beseitigt Defekt A.
    2. **Output-Ring mit Priming** (N ≥ 3). C++ startet den Drain erst, wenn ≥ 2 Bloecke gefuellt sind. Damit existiert dauerhaft ≥ 1 Block Reserve — strukturelles Aequivalent zu nn_tildes Ringbuffer-Latenz, ohne In-Process-Threads. → beseitigt Defekt C.
    3. **Blockalignter Handover.** Puffer-Wechsel ausschliesslich bei `out_pos == 0`. Nie mitten in einen neuen Block einsteigen. → beseitigt die `out_pos`-Desync.
    4. **Ownership statt Flags.** Python schreibt an `out_write_head`, C++ liest an `out_read_tail`; die Indizes duerfen sich nie ueberlappen. Kein gemeinsam beschriebener Puffer mehr. → beseitigt Defekt B ersatzlos.
    5. **Fallback bei echtem Underrun.** Letzten **vollstaendigen** Block wiederholen (separate Kopie), nicht den laufenden ab beliebiger Position.

  - **Erwartete Zusatzlatenz:** 1–2 Bloecke (46–93 ms bei 2048). nn_tilde liegt in derselben Groessenordnung → kein Nachteil gegenueber der Referenz.

  - **Betroffene Dateien / Umsetzungsschritte**
    - `SharedMemoryHeader` (C++ `mab_tilde.cpp:~30-70` + Python `inference_worker.py:70-100`): Header **v4** — `input_buffer_index`/`output_buffer_index`/`is_input_ready`/`is_output_ready` ersetzt durch `in_write_head`/`in_read_tail`/`out_write_head`/`out_read_tail` + `ring_blocks`. **C++ und Python muessen gemeinsam deployed werden** (Bug 2!).
    - SHM-Groesse: `total_size` von 2× auf N× Input/Output-Bloecke (`inference_worker.py:152-164`).
    - `mab_tilde_perform64` / `mc_mab_tilde_perform64` / `mcs_mab_tilde_perform64`: Input-Gate entfernen, Ring-Indizes verwenden, Priming-Schwelle, blockalignter Handover.
    - `inference_worker.py` Hauptloop (`~1743-1812`): Ring-Konsum statt Flag-Polling, Schreiben an `out_write_head`.
    - Tests: `test_block_accumulator.cpp`, `test_multichannel_layout.cpp`, `test_shared_memory_header_compatibility.cpp`, `test_python_shared_memory.py`, `test_shared_memory_v2.py` → Header v4 + Ring-Semantik.
    - Neuer Test: Underrun-/Overrun-Verhalten (Python kuenstlich verzoegert → kein Sample-Verlust, keine Diskontinuitaet).
  - **✅ Implementiert (2026-08-12):**
    - Header v4: `ring_blocks`=4, `in_write_head`/`in_read_tail`/`out_write_head`/`out_read_tail` ersetzen `input_buffer_index`/`output_buffer_index`/`is_input_ready`/`is_output_ready`. C++/Python `static_assert`/`ctypes.sizeof` = 196 bytes.
    - SHM: 4× input blocks + 4× output blocks (vorher 2+2).
    - `t_mab_tilde.drain_block` (long, -1 = priming).
    - Drei `perform64`: Input immer ungated → `in_write_head`. Output: `drain_block` priming (-1 → silence) → block-aligned handover nur bei `out_pos==0` → advance `out_read_tail`.
    - Python: `while in_read_tail < in_write_head` konsumiert ALLE Bloecke im Ring. Output an `out_write_head`. Blockiert bei vollem Output-Ring mit Shutdown-Check.
    - **Wichtig (Bug 2):** C++ und Python muessen gemeinsam deployed sein — Header-Layout unvereinbar mit v3. → kein Sample-Verlust, keine Diskontinuitaet).

- [x] **Bug 12 – Ring-Block-Stride nutzt aktive statt maximale Kanalzahl (kein Audio bei decode)** ✅ **FIXED** (2026-08-12)
  - **Symptom:** Nach Bug 11 kein Audio mehr bei `mab~ <model> decode <bufsize>` (z.B. `freesoundloop10k_raspi_b2048_r44100_z16`). Worker startet korrekt, Extension laedt korrekt, aber kein Ton am Outlet.
  - **Verifiziert (venv):** `model.decode(torch.zeros(1,16,1))` liefert echtes Audio (abs max 0.36) — Stille war **nicht** erwartetes Modellverhalten. `infer_method()` mit exakt der Shape aus der SHM liefert ebenfalls korrektes Audio (abs max 0.36) — der Bug liegt **nicht** in der Inferenz.
  - **Ursache:** `mab_tilde_perform64`/`mc_mab_tilde_perform64`/`mcs_mab_tilde_perform64` berechneten den Byte-Abstand zwischen Ring-Slots aus `x->channels_in`/`x->channels_out` (**aktive** Methode, z.B. decode: co=1). Python (`SharedMemoryManager.__init__`) allokiert jeden Ring-Slot aber mit der **maximalen** Kanalzahl über alle Methoden (`compute_layout()`), damit ein Methodenwechsel nie ein SHM-Remapping braucht (z.B. musicnet: encode co=16 → `max_channels_out=16`). Fuer decode (co=1 ≠ max=16) driftet der C++-Stride (2048 Floats) 16× von Pythons realem Slot-Abstand (32768 Floats) ab.
    - Ring-Slot 0 liegt bei Offset 0 → **zufällig** korrekt (deshalb spielte der *erste* 2048-Sample-Block/46 ms hörbar Audio).
    - Ring-Slot 1–3 (bei `ring_blocks=4`) lesen C++-seitig aus fremdem Speicher (ungeschriebene Kanal-Zeilen von Slot 0, seit SHM-Erzeugung nullinitialisiert) → dauerhafte Stille ab Block 2.
    - Fuer `encode` (ci=1 ≠ max_in=16) betrifft derselbe Fehler die Input-Seite; fuer `forward` (ci=co=1) beide Seiten. Bug existierte bereits im alten Ping-Pong-Design (v3/A1) fuer den ungeraden Puffer-Index, wurde dort aber vermutlich durch den Bug-10-Teilfix (Block-Looping) und Zufall (Bug-5.8-Test nutzte ein Modell/Timing, bei dem der Effekt nicht auffiel) maskiert.
  - **Fix:** Neue Header-Felder `max_channels_in`/`max_channels_out` (konstant, von Python einmalig in `create()` aus den Konstruktor-Parametern gesetzt = die MAX-Werte). Alle drei `perform64` nutzen jetzt `x->header->max_channels_in`/`max_channels_out` für den Ring-Slot-Stride; `block_accumulate_write`/`read` erhalten weiterhin die **aktive** `channels_in`/`channels_out` (bzw. `total_ci`/`total_co` bei mcs.mab~) für die tatsächlich befüllten Zeilen innerhalb des (ggf. breiteren) Slots.
  - **Header v4 waechst auf 204 Bytes** (2× `uint32_t` zusaetzlich). `static_assert`/`ctypes.sizeof` aktualisiert.
  - **Tests:** Neue Regressionstests `test_shared_memory_v2.py::TestRingBlockStrideBug12` (belegen `output_size`/`input_size` == `max_channels_*` × `block_size` × 4, nicht `channels_*`(aktiv) × ...). Bestehende Header-Offset-Tests (`test_shared_memory_v2.py`, `test_block_size_extraction.py`) auf v4/204 Bytes aktualisiert. Alle 19 C++-Tests + 310 Python-Tests grün (129 skipped, unveraendert).
  - **Dateien:** `mab_tilde.cpp:40-78` (Header-Struct + static_assert), `mab_tilde.cpp:673-675` (mab~ Stride), `mab_tilde.cpp:~1517` (mc.mab~ Stride), `mab_tilde.cpp:~1864-1867` (mcs.mab~ Stride + n_batches), `inference_worker.py:74-97` (Header-Struct), `inference_worker.py:~278-283` (create() setzt max_channels_in/out).
  - **Offen:** Max-Runtime-Test durch User (`mab~ freesoundloop10k_raspi_b2048_r44100_z16 decode 2048`, kontinuierliches Audio statt einzelnem 46 ms Blip).
  - **Nachtrag (2026-08-12):** Runtime-Test durchgefuehrt → Bug 12 war real und ist behoben, **reicht aber nicht**. Verbleibende Defekte sind Max-seitig, siehe **Bug 13**.

- [x] **Bug 13 – `mab~` dynamischer Inlet-Rebuild: Crash + veraltete DSP-Chain** ✅ **FIXED** (2026-08-12)

  - **Fix U2 (Crash):** `perform_active`-Guard + `is_bypass`-Bypass in `apply_io`. Alle 3 `perform64` nutzen `InterlockedIncrement`/`Decrement` an jedem Entry/Exit. `apply_io` setzt `is_bypass=1` → wartet auf `perform_active==0` → rebuild → `dirty`-Message an Patcher → clear bypass. Kein Use-After-Free mehr, weil `object_free`/`outlet_new` nur laufen wenn kein Audio-Thread in `ins[]`/`outs[]` iteriert.
  - **Fix U1 (numins=1):** `object_method(patcher, gensym("dirty"))` nach `dsp_resize` erzwingt Chain-Recompile. `dsp_free` war der falsche Ansatz (zerstoert Chain → Crash beim naechsten Audio-Tick). `dirty` ist deklarativ: Max baut die Chain zum naechsten sicheren Zeitpunkt neu mit korrektem `numins`.
  - **Ring-Reset:** `in_pos=0, out_pos=0, drain_block=-1` in allen 3 `dsp64` und in `apply_io` → sauberes Priming nach jedem Recompile.
  - **Betroffene Dateien:** `mab_tilde.cpp:156` (perform_active), `:642-748` (3× perform64), `:844-885` (apply_io), `:588-591,1482-1485,1838-1841` (3× dsp64).

- [x] **Bug 14 – `expected_new`-Truncation bei decode/prior mit aktivem ConvStreamingContext** ✅ **FIXED** (2026-08-12)

  - **Fix:** `infer_method()`: fuer `decode`/`prior` jetzt `expected_new = block_size` statt der Ratio-Formel. Der History-Prepend operiert auf der Latent-Seite, die Output-Domaene ist unabhaengig von `in_ratio`.
  - **Dateien:** `inference_worker.py:1001-1003`.

- [x] **Bug 15 – Worker-Timeout beim ersten (kalten) Load** ✅ **FIXED** (2026-08-13)
  - **Symptom:** Erster Patch-Load wirft `Timeout waiting for Python worker`. Nach Schliessen + erneutem Oeffnen des Patches funktioniert es. Betroffen v.a. grosse Modelle (z.B. `thirdModelTest3000Epoche.ts`, 48 MB).
  - **Ursache:** Ready-Event wird vom Worker erst NACH `import torch` + `load_model()` gesetzt (`inference_worker.py:1581`). `init_worker` wartete hart 10 s (`WaitForSingleObject(ready_event, 10000)`). Kalter Start (leerer Datei-Cache, erster PyTorch-Import, Windows-Defender-Scan der frischen `.mxe64`/`.py`/`.ts`) summiert > 10 s; zweiter Load ist warm → < 10 s.
  - **Fix (mab_tilde.cpp:595-673):** Robustes Warten statt eines einzelnen `WaitForSingleObject`: Poll alle 100 ms bis 120 s Gesamt-Timeout; bricht sofort ab, wenn der Worker-Prozess vor dem Ready-Signal stirbt (`GetExitCodeProcess` → Exit-Code wird geloggt); Info-`post()` nach 10 s (`"Worker still starting (cold start / model load) - please wait..."`).
  - **Dateien:** `mab_tilde.cpp:595-673` (`init_worker`).
  - **Test:** Build + alle 22 C++-Tests gruen. Max-Runtime-Verifikation (kalter Erst-Load) offen.

---

## Max-Runtime-Verifikation

- [ ] **V1 – decode-Layout** `[mab~ musicnet.ts decode 2048]` → 16 latent in, 1 audio out, keine dropouts
  - `mab_tilde.cpp:511-596`, `inference_worker.py:1516-1555`
  - Bug 13 behoben (2026-08-12): thread-sicherer Rebuild + `dirty`-Recompile. V1 jetzt testbar.
  - **Abnahme:** `[noise~]` auf alle 16 Inlets, jeder muss hoerbar wirken. **Kein statisches Latent** (Bug 13 U3: faellt in ~0.4 s auf Stille).
- [ ] **V2 – forward** `[mab~ musicnet.ts forward]` → 1 in/1 out
  - Gleiche Dateien
  - Hinweis: `forward` ist 1-in-1-out → kein IO-Rebuild → von Bug 13 **nicht** betroffen (B4-Skip greift, `mab_tilde.cpp:818`). Guter Isolationstest fuer Ring v4 (Bug 11/12) ohne die Inlet-Problematik.
- [ ] **V3 – encode** `[mab~ musicnet.ts encode]` → 1 audio in, 16 latent out
  - Gleiche Dateien
  - Betroffen von Bug 13 auf der **Outlet**-Seite (1→16 Outlets ⇒ `rebuild_io` mit `object_free`, U2).
- [ ] **V4 – Methodenwechsel** `method decode`/`method encode` zur Laufzeit
  - `mab_tilde.cpp:1008-1021` (mab_tilde_method)
  - Haengt von Bug 13 Schritt 4/5 ab (Runtime-Layoutwechsel ist derzeit der Crash-Pfad).
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

## Refactoring

- [x] **R1 – `mab~`-Klasse komplett entfernen** ✅ **DONE** (2026-08-12)

  **Begründung:** `mc.mab~` deckt 95 % aller Use-Cases mit stabiler 1-MC-Inlet-Architektur
  ohne `dsp_resize`/`dsp_free`/`dirty`. `mab~` (N diskrete Inlets → Rebuild) ist eine fragile
  Sonderkonfiguration die Bug 13 erst verursacht hat. Der einzig echte Mehrwert von `mab~`
  — 16 verschiedene Signalquellen an Einzel-Inlets — ist mit `[mc.pack~ 16]` → `[mc.mab~]`
  trivial nachbaubar.

  **Was fällt weg (Code):**

  | Symbol | Datei:Zeile | Grund |
  |--------|-------------|-------|
  | `mab_tilde_new` | `mab_tilde.cpp:~340` | mab~-Konstruktor; Void-Mode-Logik wandert in mc-Konstruktor |
  | `mab_tilde_dsp64` | `mab_tilde.cpp:~588` | triviale 1-Zeilen-Funktion; mc/mcs haben eigene |
  | `mab_tilde_perform64` | `mab_tilde.cpp:~642` | diskretes Inlet-Routing (ins[0..15]); MC nutzt flaches MC-Routing |
  | `mab_tilde_assist` | `mab_tilde.cpp:~554` | Inlet-Labels; mc/mcs brauchen eigene (kürzer) |
  | `mab_tilde_free` | `mab_tilde.cpp:~489` | **Shared** — wird auch von mc/mcs verwendet → umbenennen, nicht löschen |
  | `#else`-Branch in `ext_main` | `mab_tilde.cpp:~270` | mab~-Klassenregistrierung; 3-Wege→2-Wege |
  | `mab_tilde_class` | `mab_tilde.cpp:~80` | static-Klassenpointer nur noch mc+mcs |

  **Was fällt weg (Struct-Felder):**

  | Feld | Grund |
  |------|-------|
  | `is_mc` | Nach R1 immer 1 → durch `is_mcs` ersetzt (mc=0, mcs=1) |
  | `is_mcs` | bleibt (mc vs mcs) |

  **Was wird vereinfacht:**

  | Stelle | Vorher | Nachher |
  |--------|--------|---------|
  | `apply_io` io-Berechnung | `x->is_mcs ? mcs_batches : (is_mc ? 1 : model_in)` | `x->is_mcs ? mcs_batches : 1` |
  | `mab_tilde_prefix` | 3 Fälle (mcs/mc/mab) | 2 Fälle (mcs/mc) |
  | `apply_io` B4-Skip | `last_io_in/out`-Tracking | mc immer 1-in-1-out → Skip immer aktiv, kein Rebuild nötig |
  | `apply_io` Crash-Schutz | `dsp_free`+`dirty` für mab | mc triggert nie einen Rebuild → Schutzpfad bleibt aber wird nie betreten |
  | `init_worker` argbuf | `x->is_mcs ? mcs_batches : 1` | unverändert (mc sendet n_batches=1) |
  | `rebuild_io` | `is_mc`-Flag für "multichannelsignal" | immer MC → Flag kann entfallen |

  **Was bleibt (Shared, von allen verwendet):**
  - `t_mab_tilde` Struct (minus `is_mc`)
  - `mab_tilde_enable`, `gpu`, `reload`, `dump`, `set`, `get`, `method`, `load`, `anything`
  - `mab_tilde_apply_io`, `mab_tilde_check_crash`, `mab_tilde_gpu_reload_done`
  - `mab_tilde_rebuild_io` (wird nie mit geändertem io_in/io_out aufgerufen → B4-Skip)
  - `init_worker`, `init_worker_thread`, `mab_enqueue_control`
  - `mc_*` und `mcs_*` Funktionen (komplett)
  - `SharedMemoryHeader`, `ControlRingBuffer`, alle v4-Felder
  - `block_accumulator.h`

  **Build:**
  - CMakeLists.txt: Target `mab_tilde` (MODULE) entfernen
  - CMakeLists.txt: `mab_tilde_lib` (STATIC) bleibt für Tests (enthält Shared-Code)
  - `MC_MAB_TILDE_MODULE`/`MCS_MAB_TILDE_MODULE`-Defines bleiben (2-Wege)
  - Tests: `test_mab_tilde_new`, `test_mab_tilde_dsp64`, `test_mab_tilde_perform64`,
    `test_mab_tilde_free`, `test_mab_tilde_assist` — falls sie mab~-spezifisch sind → entfernen

  **Deploy:**
  - `deploy.ps1`: `mab~.mxe64`-Copy entfernen
  - VSCode-Task: Build-Targets anpassen

  **Reihenfolge (geschätzt 2–3 h):**
  1. `ext_main`: `#else`-Branch + `mab_tilde_class` entfernen, 3-Wege→2-Wege
  2. `mab_tilde_new` + `mab_tilde_perform64` + `mab_tilde_dsp64` + `mab_tilde_assist` löschen
  3. `mab_tilde_free` → `mab_tilde_shared_free` umbenennen (wird von mc/mcs genutzt)
  4. `is_mc`-Feld entfernen, `perform_active` bleibt
  5. `apply_io`: io-Berechnung vereinfachen, `is_mc`-Check entfernen
  6. `mab_tilde_prefix`: 3→2 Fälle
  7. `rebuild_io`: `is_mc`-Flag entfernen (immer MC)
  8. CMakeLists.txt: mab~-Target entfernen
  9. `deploy.ps1`: mab~-Zeile entfernen
  10. Tests: mab~-spezifische Tests identifizieren und entfernen/anpassen
  11. Build + alle Tests + Max-Runtime (mc + mcs)

## Feature Requests

- [x] **FR4 – Max-Package-Struktur standardisieren (help, icon, package-info)** ✅ **DONE** (2026-08-12)

  **IST-Zustand:**
  - `help/mab~.maxhelp` + `help/mab.info.maxhelp` existieren im Repo, werden **nicht** deployed
  - `package-info.json` liegt in `externals/` (falsch, gehört ins Package-Root)
  - `models/` (6 Demo-Modelle, 0.2 MB) liegen nur im Max-Package, nicht im Repo
  - Kein `icon.png`, keine `docs/`, keine `extras/`
  - Altes `mab~.mxe64` liegt noch im Max-Package-`externals/`

  **Referenz:** nn_tilde-Package + 10 andere Packages analysiert. Standard-Layout:

  ```
  mab_tilde/                         # Max-Package-Root
  ├── icon.png                       # 90 % aller Packages haben es
  ├── package-info.json              # Pflicht, mit "filelist" für Uninstall
  ├── README.md / license.txt        # Optional, aber üblich
  ├── externals/                     # .mxe64 (Pflicht)
  ├── help/                          # .maxhelp (fast alle)
  ├── docs/                          # .maxref.xml (viele)
  ├── examples/                      # Beispiel-Patches (viele)
  ├── extras/                        # Overview/Navigation (viele)
  ├── media/                         # Audio/Images (einige)
  ├── patchers/                      # Abstractions/Sub-Patchers (einige)
  └── support/                       # inference_worker.py, DLLs
  ```

  **`package-info.json`-Standardfelder:**
  ```json
  {
    "name": "mab_tilde",
    "displayname": "mc.mab~ / mcs.mab~",
    "version": "1.0.0",
    "author": "mab_tilde",
    "description": "Neural audio processing with RAVE/AFTER models",
    "tags": ["neural", "audio", "machine learning", "rave"],
    "website": "",
    "max_version_min": "9.0",
    "max_version_max": "none",
    "os": {
      "windows": { "min_version": "10", "platform": ["x64"] }
    },
    "filelist": {
      "externals": ["mc.mab~.mxe64", "mcs.mab~.mxe64", "mab.info.mxe64"],
      "help": ["mc.mab~.maxhelp", "mcs.mab~.maxhelp", "mab.info.maxhelp"],
      "support": ["inference_worker.py"]
    },
    "c74install": 1
  }
  ```

  **Umsetzungsplan (geschätzt 1–2 h):**

  **Schritt 1 – `package/`-Verzeichnis im Repo anlegen:**
  ```
  package/                          # Wird 1:1 ins Max-Package-Root deployed
  ├── package-info.json             # Neu, mit korrekten Metadaten + filelist
  ├── icon.png                      # Neu, 128×128 (z.B. RAVE-Logo-Stilisierung)
  └── help/
      ├── mc.mab~.maxhelp           # Kopie von help/mab~.maxhelp, Referenzen aktualisiert
      ├── mcs.mab~.maxhelp          # Kopie von mc.mab~.maxhelp, "mcs" statt "mc"
      └── mab.info.maxhelp          # Kopie von help/mab.info.maxhelp, unverändert
  ```
  - Hilfe-Dateien: Inhaltlich ok, nur Objekt-Referenzen von `mab~` → `mc.mab~`/`mcs.mab~` ändern
  - `icon.png`: Einfaches Platzhalter-Icon (z.B. farbiger Kreis mit "AI"), später ersetzbar
  - Altes `help/`-Verzeichnis im Repo-Root **löschen** (ersetzt durch `package/help/`)

  **Schritt 2 – `deploy.ps1` erweitern:**
  ```powershell
  # 3. Deploy package files (help, icon, package-info)
  Copy-Item "$projectRoot\package\*" $targetDir -Recurse -Force
  ```
  - Kopiert `package-info.json` → Package-Root (nicht mehr `externals/`)
  - Kopiert `help/` → `help/`
  - Kopiert `icon.png` → Package-Root

  **Schritt 3 – Alte Dateien im Max-Package bereinigen:**
  ```powershell
  # Cleanup
  Remove-Item "$externals\package-info.json" -Force -ErrorAction SilentlyContinue
  Remove-Item "$externals\mab~.mxe64" -Force -ErrorAction SilentlyContinue
  ```
  - `package-info.json` aus `externals/` löschen (wird jetzt ins Root deployed)
  - `mab~.mxe64` löschen (R1-Nacharbeit)

  **Schritt 4 – Demo-Modelle:**
  - `models/` **nicht** ins Repo (Binary Bloat, 0.2 MB Demo + potenziell große Produktiv-Modelle)
  - `models/` **nicht** in `package/` (würde bei Deploy überschrieben)
  - Option: `deploy.ps1` prüft ob `models/musicnet.ts` existiert, sonst aus `D:\AI-Models\ts models\` kopieren
  - Oder: `models/` bleibt manuell verwaltet (User kopiert Modelle selbst)
  - `musicnet.ts` (0-Byte-Platzhalter) durch echte Datei ersetzen oder löschen

  **Schritt 5 – Build-Integration:**
  - Help-Dateien sind statische JSON-Dateien (kein Build nötig)
  - `deploy.ps1` kopiert sie direkt aus `package/` ohne CMake
  - Optional: CMake `configure_file()` für `package-info.json` um Version/Strings aus CMake-Variablen zu setzen

  **Nicht im Scope (später):**
  - `docs/` — `.maxref.xml`-Referenzdokumentation (aufwändig, nn_tilde hat sie)
  - `examples/` — Beispiel-Patches
  - `extras/` — Overview-Patch (nn_tilde hat `nn~ Overview.maxpat`)
  - `patchers/` — Sub-Patchers für Help (nn_tilde hat `help_hub.maxpat`, `rave_help.maxpat`)
  - `media/` — Audio-Beispiele für Help-Demos

