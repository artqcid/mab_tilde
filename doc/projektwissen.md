# Projektwissen mab_tilde – manuell gepflegt

_Dieses Dokument enthält Architekturwissen, das der automatische Chunker nicht
erfassen kann (Struct-Layouts, Konstanten, Threading-Modell, Message-Flows).
Wird von Coding-Agents zusammen mit `code_wiki.md` pro Session gelesen._

---

## Zentrale Datenstrukturen

### `t_mab_tilde` (mab_tilde.cpp:68-125) – Haupt-Objekt von `mab~` und `mc.mab~`

```c
typedef struct _mab_tilde {
    t_pxobject ob;              // Max MSP Basis-Objekt (DSP)
    long is_ready;              // 1 = Python verbunden & bereit
    long is_bypass;             // 1 = Bypass (kein Audio-Durchsatz)
    
    // Threading & Prozess
    std::thread* init_thread;   // Hintergrund-Thread für Worker-Start
    HANDLE python_process;      // Handle des Python-Worker-Prozesses
    HANDLE ready_event;         // "MabReadyEvent_{instance_id}" – Python signalisiert Bereitschaft
    HANDLE input_ready_event;   // "MabInputReadyEvent_{instance_id}" – C++ signalisiert neue Input-Daten (A4)
    HANDLE hMapFile;            // Windows Shared Memory Handle

    // Shared Memory Pointer
    SharedMemoryHeader* header; // Zeiger auf gemappten Header (IPC!)
    float* p_input;             // Zeiger auf Input-Buffer (double-buffered)
    float* p_output;            // Zeiger auf Output-Buffer (double-buffered)
    ControlRingBuffer* p_control; // Zeiger auf Control-Ringpuffer
    
    // Argumente (aus Objekt-Instanziierung)
    char model_path[256];       // Pfad zum .ts-Modell
    char method_name[64];       // Aktive Methode ("forward"/"encode"/"decode"/"prior")
    long buffer_size;           // Block-Größe (Default 512)
    long gpu;                   // 1 = CUDA, 0 = CPU
    long cores;                 // PyTorch-Inferenz-Threads (Default 2, Clamp 1..64)
    
    // Runtime-Zustand
    long num_channels;          // Legacy: Output-Kanäle
    
    // Phase 3: Method-aware IO (aus Header v2 gecached)
    char active_method[64];     // Aktiver Methodenname
    uint32_t active_method_id;  // Stable Hash für atomaren Compare
    long channels_in;           // Inlet-Anzahl der aktiven Methode
    long channels_out;          // Outlet-Anzahl der aktiven Methode
    long in_pos;                // Input-Akkumulationsposition (block_accumulator)
    long out_pos;               // Output-Drain-Position (block_accumulator)
    long method_pending;        // 1 = IO-Rebuild via qelem ausstehend
    
    // Control-Message-Puffer
    char control_buffer[1024];  // Puffer für anything-Weiterleitung
    long control_size;          // Größe der Control-Nachricht
    
    // Main-Thread-Kommunikation
    t_qelem* io_qelem;          // Qelem für mab_tilde_apply_io (IO-Rebuild auf Main-Thread)
    t_clock* crash_clock;       // periodischer Crash-Check (100ms, Main-Thread, A2)
    
    // Phase 5: mc.mab~ (Multichannel) support fields
    long is_mc;                // 1 = mc.mab~ mode, 0 = mab~ mode
    long channel_map[16];      // per-inlet channel count (MC mode, max 16 inlets)
    long n_batches;            // fixed output channels from `chans` attribute (0 = auto)

    // Phase 6: mcs.mab~ (Batched Multichannel) support fields
    long is_mcs;               // 1 = mcs.mab~ mode, 0 = mab~/mc.mab~ mode
    long mcs_batches;          // number of batch inlets/outlets (mcs.mab~, 1..16)
} t_mab_tilde;
```

**Prefix-Helper:** `mab_tilde_prefix(x)` → `"mcs.mab~"` / `"mc.mab~"` / `"mab~"` je nach `is_mcs`/`is_mc` (für alle `post()`-Aufrufe).

**Lebenszyklus:**
1. `mab_tilde_new` → allokiert, setzt bypass=1, startet `init_worker_thread` (detached)
2. `init_worker_thread` → ruft `init_worker` → startet Python, wartet auf `ready_event`
3. Bei Erfolg: bypass=0, is_ready=1, qelem → `mab_tilde_apply_io` baut IO auf
4. `mab_tilde_free` → shutdown_flag, WaitForSingleObject(500ms), TerminateProcess, Cleanup

### `t_mab_info` (mab_info.cpp:29-51) – mab.info Modell-Inspektor

```c
typedef struct _mab_info {
    t_object ob;                // Max MSP Basis-Objekt (kein DSP!)
    
    void* out_path;             // Outlet 1: model path (symbol)
    void* out_methods;          // Outlet 2: verfügbare Methoden (symbol)
    void* out_attributes;       // Outlet 3: verfügbare Attribute (symbol)
    void* out_params;           // Outlet 4: processing parameters (symbol + ints)
    void* out_dict;             // Outlet 5: dict output (dictionary)
    
    char model_path[MAX_PATH];  // Pfad zum Modell
    
    long has_info;              // 1 = Query-Ergebnis liegt vor
    WorkerModelInfo info;       // Gecachtes Query-Ergebnis
    char dict_json[16384];      // Dict-JSON-Puffer (MAB_INFO_DICT_JSON)
    
    std::thread* query_thread;  // Hintergrund-Thread für --query
    t_qelem* result_qelem;      // Qelem für Ergebnis-Ausgabe auf Main-Thread
    long query_pending;         // 1 = Query läuft

    // P11: download/delete/print_available_models (standalone Worker-Läufe)
    std::thread* cmd_thread;    // Hintergrund-Thread für --download/--delete/--list
    t_qelem* cmd_qelem;         // Qelem für mab_info_apply_cmd (Main-Thread)
    long cmd_pending;           // 1 = Kommando läuft
    char cmd_args[1024];        // Argument-Zeile für worker_launch
    char cmd_result[8192];      // Worker-stdout (Ergebniszeilen)
    char cmd_error[512];        // Launch-/Netzwerk-Fehler
} t_mab_info;
```

**P11-Message-Flow (download/delete/print_available_models):**
```
Max Message → mab_info_download/delete/print → mab_info_run_command() (Main-Thread)
    → cmd_thread (detached std::thread): worker_launch("--download ...", capture_stdout=true)
    → stdout einlesen (mab_info_drain_stdout, 90s Timeout) → x->cmd_result/cmd_error
    → qelem_set(cmd_qelem) → mab_info_apply_cmd (Main-Thread)
    → Erfolg: Zeilen auf Outlet 1 (path) | Fehler: object_error (kein Crash)
```

### `SharedMemoryHeader` v3 (mab_tilde.cpp:38-67, inference_worker.py:61-95)

192 Bytes, Feld-Reihenfolge muss C++ ↔ Python exakt übereinstimmen.
Layout: 9×uint32(36) + method[52] + method_id(4) + 3×uint32(12) + 2×uint32(8) +
`channel_map[16]`(64) + 4×long(16).

Felder: magic, version(3), block_size, num_channels, channels_in, channels_out,
latent_size, input_ratio, output_ratio, method[52], method_id, input_offset,
output_offset, control_offset, input_buffer_index, output_buffer_index,
**channel_map[16]** (Phase 5: Kanäle pro mc.mab~-Inlet, Offsets 112–175),
is_input_ready(176), is_output_ready(180), is_python_ready(184),
shutdown_flag(188).

### `ControlRingBuffer` (mab_tilde.cpp:24-28, inference_worker.py:95-101)

Lock-free SPSC Ringpuffer: C++ schreibt `head`, Python liest `tail`.
256 Slots × 256 Bytes.

### `WorkerModelInfo` (worker_launch.h:24-37)

```c
struct WorkerModelInfo {
    char model_path[MAX_PATH];
    char method_names[4096];   // komma-separiert
    char attribute_names[4096];
    char params_text[4096];    // "method: ci=X ri=Y co=Z ro=W ..."
};
```

---

## Threading-Modell

| Thread | Funktionen | Einschränkungen |
|--------|-----------|-----------------|
| **Max Main Thread** | `ext_main`, `mab_tilde_new`, `mab_tilde_free`, `mab_tilde_apply_io`, `mab_tilde_check_crash`, Message-Handler | Darf `dsp_resize`/`outlet_new`/`object_free` aufrufen |
| **Audio Thread** | `mab_tilde_perform64`, `mab_tilde_dsp64` | **KEINE** OS-Locks, nur Atomics + `Interlocked*` |
| **Init Thread** (detached) | `init_worker_thread` → `init_worker` | Startet Python, wartet auf `ready_event` (10s Timeout) |
| **Python Worker** | `inference_worker.py:main()` | `BELOW_NORMAL_PRIORITY_CLASS`, Core 0 exkludiert |
| **mab.info Query Thread** | `mab_info_query_thread` | Führt `worker_launch(--query)` aus, parst stdout |

**Kritische Regel:** `dsp_resize` + `outlet_new`/`object_free` NUR auf dem Max Main Thread!
Audio-Thread scheduled IO-Rebuilds via `qelem_set(x->io_qelem)`.

---

## Message-Flows

### Modell-Initialisierung
```
Max Patch: [mab~ model.ts decode 2048]
    ↓ Max Main Thread
mab_tilde_new() → speichert args, startet init_worker_thread (detached)
    ↓ Init Thread
init_worker() → worker_launch() → CreateProcessW(python.exe inference_worker.py ...)
    ↓ Python Worker
SharedMemoryManager.create() → CreateFileMappingW + MapViewOfFile
Modell laden → Header v2 schreiben → SetEvent(ready_event)
    ↓ Init Thread
WaitForSingleObject(ready_event) → OpenFileMappingW → MapViewOfFile
bypass=0, is_ready=1, qelem_set(io_qelem)
    ↓ Max Main Thread (via qelem)
mab_tilde_apply_io() → dsp_resize + outlet_new → IO steht
```

### Audio-Durchsatz (pro DSP-Tick)
```
    ↓ Audio Thread (perform64)
block_accumulate_write(double→float) → p_input
InterlockedExchange(&header->is_input_ready, 1)
SetEvent(input_ready_event)  // weckt Python (A4)
    ↓ Python Worker
WaitForSingleObject(input_ready_event) → infer_method() → Modell-Forward
Ergebnis in p_output → InterlockedExchange(&header->is_output_ready, 1)
    ↓ Audio Thread (nächster Tick oder async)
block_accumulate_read(float→double) → outs[]
```

### Message-Weiterleitung (set/get/method/reload/anything)
```
Max Message → mab_tilde_set/get/method/etc → mab_enqueue_control() → ControlRingBuffer
    ↓ Audio Thread (perform64)
is_output_ready prüfen → ggf. Control-Nachrichten verarbeiten
    ↓ Python Worker
ControlRingBuffer.dequeue() → Nachricht parsen → Aktion ausführen
```

---

## Konstanten

| Konstante | Wert | Datei:Zeile | Bedeutung |
|-----------|------|-------------|-----------|
| `MAX_CHANNELS` | 16 | mab_tilde.cpp:18 | Maximale Kanalzahl für Inlets/Outlets |
| `MAX_BLOCK_SIZE` | 4096 | mab_tilde.cpp:19 | Maximale Audio-Blockgröße in Samples |
| `CONTROL_RING_SIZE` | 256 | mab_tilde.cpp:20 | Anzahl Slots im Control-Ringpuffer |
| `CONTROL_MSG_SIZE` | 256 | mab_tilde.cpp:21 | Bytes pro Control-Nachricht |
| `MAB_INFO_DICT_JSON` | 16384 | mab_info.cpp:25 | JSON-Puffer für Dict-Output |
| `MAGIC_NUMBER` | 0x4D414254 | inference_worker.py:50 | 'MABT' – Header-Validierung |
| `MODEL_API_ROOT` | URL | inference_worker.py:55 | IRCAM Forum API für Model-Download |
| `RAG_SCHEMA_VERSION` | 4 | mab_mcp_server.py:66 | RAG-DB-Schema-Version |
| `Header-Größe v2` | 128 Bytes | mab_tilde.cpp:59-60 | static_assert-gesichert |

---

## Build-Targets (CMakeLists.txt)

| Target | Typ | Output | Quellen |
|--------|-----|--------|---------|
| `mab_tilde` | MODULE | `mab~.mxe64` | mab_tilde.cpp, worker_launch.cpp, max_path_resolve.cpp |
| `mab_tilde_lib` | STATIC | (nur für Tests) | Gleiche Quellen |
| `mc_mab_tilde` | MODULE | `mc.mab~.mxe64` | mab_tilde.cpp (mit `MC_MAB_TILDE_MODULE`), worker_launch.cpp, max_path_resolve.cpp |
| `mcs_mab_tilde` | MODULE | `mcs.mab~.mxe64` | mab_tilde.cpp (mit `MCS_MAB_TILDE_MODULE`), worker_launch.cpp, max_path_resolve.cpp |
| `mab_info` | MODULE | `mab.info.mxe64` | mab_info.cpp, worker_launch.cpp, max_path_resolve.cpp |
| `test_worker_launch` | EXE | build/Debug/test_worker_launch.exe | test_worker_launch.cpp + worker_launch.cpp |
| 18 weitere Tests | EXE | build/Debug/test_*.exe | Jeweils test/test_*.cpp |

**Phase 5/6 – Mehrfachkompilierung:** `mc.mab~.mxe64` und `mcs.mab~.mxe64` werden aus der **gleichen** `mab_tilde.cpp` kompiliert wie `mab~.mxe64`, aber mit `target_compile_definitions(... PRIVATE MC_MAB_TILDE_MODULE)` bzw. `MCS_MAB_TILDE_MODULE`. Der `#if defined(MCS_MAB_TILDE_MODULE) / #elif defined(MC_MAB_TILDE_MODULE) / #else`-Block in `ext_main` registriert dann nur die jeweilige Klasse.

**Build-Befehle:**
```powershell
cmake --preset debug          # Konfigurieren
cmake --build --preset debug  # Kompilieren (Output: build/Debug/mab~.mxe64)
```

**Deploy nach Max 9:**
```powershell
Copy-Item build\Debug\mab~.mxe64 "$env:USERPROFILE\Documents\Max 9\Packages\mab_tilde\externals\"
Copy-Item build\Debug\mc.mab~.mxe64 "$env:USERPROFILE\Documents\Max 9\Packages\mab_tilde\externals\"
Copy-Item build\Debug\mcs.mab~.mxe64 "$env:USERPROFILE\Documents\Max 9\Packages\mab_tilde\externals\"
Copy-Item build\Debug\mab.info.mxe64 "$env:USERPROFILE\Documents\Max 9\Packages\mab_tilde\externals\"
Copy-Item inference_worker.py "$env:USERPROFILE\Documents\Max 9\Packages\mab_tilde\support\"
```

---

## Datei-Zweck-Übersicht (nur Projektcode, kein SDK)

| Datei | Zweck | Sprache |
|-------|-------|---------|
| `mab_tilde.cpp` | Haupt-External `mab~`: Max-API, DSP, IPC, Messages | C++ |
| `mab_info.cpp` | Modell-Inspektor `mab.info`: Query-Mode, Dict-Output | C++ |
| `worker_launch.cpp/.h` | Shared: Python-Prozess-Start, venv-Auflösung, Info-Block-Parsing | C++ |
| `max_path_resolve.cpp/.h` | Shared: Modell-Pfad-Auflösung (relativ + Max-Suchpfad) | C++ |
| `block_accumulator.h` | Header-only: SIMD float↔double + Block-Akkumulation | C++ |
| `buffer_manager.h` | P7-Vorbereitung: BufferRef/BufferManager-Platzhalter (buffer_reference → Phase 5) | C++ |
| `inference_worker.py` | Python-Backend: SHM, Modell-Load, Inferenz-Loop, Attribute | Python |
| `mab_mcp_server.py` | MCP-Server: RAG-DB, Code-Chunking, Wiki-Generierung, Modell-Inspektion | Python |
| `CMakeLists.txt` | Build: 4 Libraries + 19 Tests, Native Max SDK (kein min-devkit) | CMake |
| `CMakePresets.json` | CMake-Presets: debug/release, VS 18 2026 x64 | JSON |
| `requirements.txt` | Python-Deps: torch, numpy, mcp, fastmcp, onnxruntime | Text |
| `setup_env.bat` | Windows: venv erstellen + pip install | Batch |
| `.ragignore` | Pfade, die `index_project_code` ausschließt (min-api, build, .venv) | Text |
| `.mcp.json` | MCP-Konfiguration für VS Code (Claude-Code-Format; opencode ignoriert diese Datei) | JSON |
| `opencode.json` | opencode-Konfiguration: Agents, Modelle, Permissions, Compaction + MCP-Registrierung (`mab-rave-assistant`, Key `mcp`) | JSON |

---

## Max-SDK-Referenz (kompakt)

| Falscher Name | Korrekter Name | Verwendung |
|---------------|----------------|------------|
| `getsym(...)` | `gensym("...")` | Symbol-Erstellung |
| `atom_getint(...)` | `atom_getlong(...)` | Atom als 64-bit Integer lesen |
| `atom_type(...)` | `atom_gettype(...)` | Atom-Typ abfragen |
| `class_dspinit64(...)` | `class_dspinit(c)` | DSP-Initialisierung |
| `CLASS_NOFLOAT` | `0L` | class_new Flags |
| `bind64` | `gensym("dsp_add64")` | Perform-Methoden-Registrierung |
| `int main()` | `void ext_main(void* r)` | Max External Einstiegspunkt |

**Wichtige Max-SDK-Funktionen:**
- `class_new("name", new_fn, free_fn, sizeof, flags, A_GIMME, 0)` – Klasse registrieren
- `class_addmethod(c, fn, "msg", A_LONG, 0)` – Message-Handler
- `class_dspinit(c)` – DSP-fähig machen
- `class_register(CLASS_BOX, c)` – Klasse bei Max anmelden
- `object_alloc(c)` – Instanz allokieren (ruft KEINE Konstruktoren!)
- `dsp_setup(px, num_inlets)` – Standard-Inlets (später via dsp_resize anpassbar)
- `outlet_new(x, "signal")` – Signal-Outlet
- `outlet_new(x, NULL)` – Message-Outlet
- `dsp_resize(px, num_inlets)` – Inlet-Anzahl ändern (NUR Main-Thread!)
- `qelem_new(x, fn)` / `qelem_set(q)` – Main-Thread-Trampolin
- `clock_new(x, fn)` / `clock_fdelay(c, ms)` – Timer (Main-Thread)
- `post("format", ...)` – Max-Konsole
- `object_error(x, "msg")` – Fehler in Max-Konsole

---

## Architektur-Entscheidungen (aus mab_dev_architecture.md)

1. **Prozess-Isolation:** Python in eigenem Prozess → Crash-Isolation, kein GIL, kein libtorch in Max
2. **Lock-Free IPC:** Windows Shared Memory + SPSC Ringpuffer + Named Events + Double-Buffering
3. **Async Init:** `mab_tilde_new` blockiert nie den Main-Thread
4. **RT Safety:** Keine OS-Locks in `perform64`, nur Atomics
5. **Method-Aware IO:** Header v2 mit `{method}_params = [ci, ri, co, ro]`
6. **Worker-Priorität:** `BELOW_NORMAL_PRIORITY_CLASS`, Core 0 exkludiert, `torch.set_num_threads(1)`

---

## Phase 5 – mc.mab~ (Multichannel)

### Design

`mc.mab~` teilt sich den `t_mab_tilde`-Struct mit `mab~` und wird aus derselben
`mab_tilde.cpp` kompiliert (Doppelkompilierung via `MC_MAB_TILDE_MODULE`).

**IO-Architektur (1-in-1-out):** Anders als nn_tilde's mc.nn~ (m_model_in
Inlets) hat `mc.mab~` IMMER genau **1 Multichannel-Inlet + 1 Multichannel-
Outlet**. Die Kanalzahl wird über das MC-System transportiert:
- `multichanneloutputs` fragt die Outlet-Kanalzahl ab → `n_batches` (chans) oder `channels_out`
- `inputchanged`/`dsp64` melden die verbundenen Inlet-Kanäle → `channel_map`
- perform64 erhält `numins` = Summe aller verbundenen Inlet-Kanäle (ein Buffer pro Kanal)

**KRITISCH für MC-Funktion — `Z_MC_INLETS`-Flag:**
Das `z_misc`-Feld des `t_pxobject` muss `Z_NO_INPLACE | Z_MC_INLETS` enthalten
(`z_dsp.h:45`: "object knows how to count channels of incoming multi-channel
signals"). Ohne `Z_MC_INLETS` liefert Max nur **Kanal 1** einer MC-Bundle an
den Inlet → alle anderen Latent-Kanäle werden im Shared-Memory-Buffer genullt.
Dieselben Flags setzt die min-api für `mc_operator_base`-Klassen
(`c74_min_operator_vector.h:120-128`). Gesetzt in `mc_mab_tilde_new` und
`mab_tilde_rebuild_io` (nach `dsp_resize`, da dieses das Flag potenziell
zurücksetzt).

**Unterschiede zu mab~:**
- `is_mc = 1` → `mab_tilde_rebuild_io` erzeugt `"multichannelsignal"`-Outlets statt `"signal"`
- MC-Callbacks: `multichanneloutputs` (Frage nach Output-Kanalzahl pro Outlet-Index) und
  `inputchanged` (Benachrichtigung über Kanalzahl-Änderung an Inlet-Index)
- `channel_map[16]` pro Inlet: `mc_mab_tilde_dsp64` liest die `count[]`-Werte aus Max'
  MC-System, `mc_inputchanged` aktualisiert sie zur Laufzeit; beide publizieren die
  Map in den `SharedMemoryHeader` (Header **v3**, Phase 5 / 5.3)
- `chans <n>`-Attribut: fixe Output-Kanalzahl in `n_batches` (0 = auto aus Modell-Layout)

**Kanal-Mismatch-Handling (5.5):**
- Weniger verbundene Kanäle als Modell-deklariert (`numins < channels_in`): die fehlenden
  Zeilen werden von `block_accumulate_write` mit Nullen gefüllt (Modell sieht Silence)
- Mehr Outlets als Modell-Kanäle (`numouts > channels_out`, z.B. `chans 2` auf Mono-decode):
  `mc_mab_tilde_perform64` liest nur `min(channels_out, numouts)` Zeilen und silencet die
  überzähligen Outlets explizit (kein Stale-Data)
- Bypass: kanalweises Passthrough (`min(numins, numouts)` Kanäle) statt nur ins[0]

### MC-Funktionsübersicht (mab_tilde.cpp)

| Funktion | Zweck |
|----------|-------|
| `mc_mab_tilde_new` (1055) | Konstruktor (is_mc=1, Void-Mode, Argument-Parsing) |
| `mc_mab_tilde_dsp64` (1200) | Liest `count[]` → `channel_map`, publiziert in Header; fasst `x->channels_in` NICHT an (kein Rebuild-Loop) |
| `mc_mab_tilde_perform64` (1233) | MC-perform: Zero-Padding fehlender Input-Kanäle, Zero-Fill überzähliger Outlets |
| `mc_multichanneloutputs` (1317) | Gibt `n_batches` (chans) oder `channels_out` zurück |
| `mc_inputchanged` (1327) | Aktualisiert `channel_map[index]`, publiziert in Header |
| `mc_mab_tilde_chans` (1347) | Setter für `n_batches` |
| `mab_tilde_apply_io` (629) | MC-Modus: immer 1-in-1-out; `channel_map` + Header-Map werden beim Rebuild zurückgesetzt |

### Threading-Regeln (Phase 5)

- `channel_map` wird von Max Main-Thread (`inputchanged`) und Audio-Thread (`dsp64`)
  geschrieben → nur `long`-Zuweisungen (atomar genug für diese Nutzung)
- `n_batches`/`is_mc` nur auf Main-Thread geschrieben, von Audio-Thread gelesen
- `header->channel_map` wird von Main-Thread (dsp64/inputchanged/apply_io) geschrieben,
  vom Python-Worker gelesen → uint32-Zuweisungen, kein Lock nötig

---

## Phase 6 – mcs.mab~ (Batched Multichannel)

### Design

`mcs.mab~` erweitert `mc.mab~` um `mcs_batches` parallele Batch-Inlets/-Outlets
(nn_tilde-Parität P9) und wird aus derselben `mab_tilde.cpp` kompiliert
(`MCS_MAB_TILDE_MODULE` → nur `mcs.mab~`-Klasse registriert).

**Arg-Reihenfolge (mcs, abweichend von mab~/mc.mab~):**
```
[mcs.mab~ model method n_batches bufsize gpu cores]   # Modell-Modus
[mcs.mab~ void n_batches bufsize]                      # Void-Modus
```
`n_batches` (Feld `mcs_batches`) = Anzahl Batch-Inlets/-Outlets (1..16, Default 1).
Feld `n_batches` bleibt wie in Phase 5 der `chans`-Override (fixe Out-Kanalzahl
pro Batch-Outlet, 0 = auto aus `channels_out`).

**IO-Architektur:** `mcs_batches` Multichannel-Inlets + `mcs_batches`
Multichannel-Outlets (jeweils `"multichannelsignal"`). Jedes Batch-Inlet trägt
`channel_map[b]` Kanäle (Modell-Layout `channels_in` pro Batch), jedes
Batch-Outlet liefert `chans` oder `channels_out` Kanäle. Max liefert die
verbundenen Kanäle **flach** in perform64: Inlet 0 zuerst, dann Inlet 1, ...

**SHM-Layout (6.3) – batch-major:**
```
Input : [n_batches × channels_in × block_size]  Zeile = b*ci + c
Output: [n_batches × channels_out × block_size] Zeile = b*co + c
```
- C++-perf64: `ins[]`-Flat-Array → Zeilen `b*ci+c` (fehlende Kanäle → Zero-Padding
  via `block_accumulate_write`); Drain Zeilen `b*co+c` → Outlets bei
  `b*per_outlet+c` (per_outlet = `chans` oder `co`); überzählige Outlet-Kanäle
  (per_outlet > co) werden explizit gesilenced
- Python: `get_numpy_input/output` liefern für `n_batches > 1` 3D-Views
  `(n_batches, ci, bs)` / `(n_batches, co, bs)`; `infer_method` macht einen
  einzigen Batched-Forward `(B, ci, bs) → (B, co, bs)` (2D-Input bleibt
  unverändert `(ci, bs) → (co, bs)`)
- Header v3 unverändert: `channel_map[16]` = Batch-Map (max. 16 Batches),
  192-Byte-static_assert bleibt

**Worker-Args:** `init_worker`-argbuf: `model method bufsize gpu n_batches
shm_name instance_id num_channels cores` (mab~/mc.mab~ senden `n_batches=1`).

### mcs-Funktionsübersicht (mab_tilde.cpp)

| Funktion | Zweck |
|----------|-------|
| `mcs_mab_tilde_new` (ab ~1390) | Konstruktor (is_mcs=1, is_mc=1, `mcs_batches`-Parsing, Void-Modus) |
| `mcs_mab_tilde_dsp64` | Liest `count[i]` pro Batch-Inlet → `channel_map`, publiziert in Header; fasst `channels_in` NICHT an |
| `mcs_mab_tilde_perform64` | Batch-Wiring `b*ci+c` (Input) / `b*co+c` (Output), Zero-Padding + Outlet-Silencing |
| `mcs_multichanneloutputs` | `chans` (n_batches) oder `channels_out` pro Outlet-Index |
| `mcs_inputchanged` | Aktualisiert `channel_map[index]`, publiziert in Header, Warnung bei `count != channels_in` |
| `mab_tilde_apply_io` | mcs: `io_in = io_out = mcs_batches` (Multichannel) |
| `mc_mab_tilde_chans` | Geteilter `chans`-Setter (prefix-neutral, mc + mcs) |

### Threading-Regeln (Phase 6)

- `mcs_batches`/`is_mcs` nur auf Main-Thread geschrieben, von Audio-Thread gelesen
- `channel_map`-Zugriffe wie Phase 5 (long-Zuweisungen, kein Lock)
- `wired`-Arrays im perform64: `const double* wired[256]` (max. 16 Batches × 16 Kanäle) – Stack, kein Heap

---

## Testing – Offline-Tests (ohne Max Runtime)

_Ergänzung 2026-08-11 durch Architect. Siehe `doc/test_strategy.md` für die
vollständige Teststrategie. Diese Sektion fasst testrelevante Wissensbausteine
aus Codeanalyse + Web-Recherche zusammen, die Dev-Agents für die
Implementierung von T1–T7 benötigen._

### Modell-Inventar & Status (23 TorchScript)

Stand: 2026-08-11. Alle Modelle in `D:\AI-Models\ts models`. Dynamisch durch
Tests gescannt; feste Liste in `test/test_model_loading.py` (`EXPECTED`).

| Typ | Modelle |
|-----|---------|
| RAVE v2 (encode/decode/forward) | birds_dawnchorus, birds_motherbird, birds_pluma, crozzoli, freesoundloop10k_raspi, humpbacks_pondbrain, marinemammals_pondbrain, mrp_strengjavera, sol_ordinario_fast, voice_hifitts, voice_jvs, voice_vctk, voice_vocalset, voice-multi, water_pondbrain |
| RAVE v2 + prior | magnets, musicnet, nasa, vintage, wheel |
| Training/Experiment | modell_30min_27915e19b0, thirdModelTest3000Epoche |
| Einfach (forward only) | wavetable |

**Block-Size:** 2048 Samples für die meisten RAVE-Modelle; 512 für birds_dawnchorus, modell_30min, sol_ordinario, thirdModelTest3000Epoche, wavetable.

**ONNX-Modelle** werden per `_onnx.ts`-Suffix ausgeschlossen.

**RAVE-Trainings-Kontexte (aus acids-ircam/rave README):**
- `--streaming`-Flag beim Export → essentiell für Echtzeit (ohne: Clicking-Artefakte)
- `--prior`-Flag beim Export → bindet einen trainierten Prior ins .ts-Modell ein
- Memory-Anforderungen: v1 ≥8GB, v2 ≥16GB, v3 ≥32GB GPU RAM
- Dateinamens-Konvention: `<name>_b<block>_r<sr>_z<latent>.ts`

### nn_tilde-Parität: Testrelevante Messages & Attribute

Aus `nn_tilde` README + `nn_base.h` — diese Messages und Attribute müssen auch
in mab~ funktionieren und sind daher Teil der Testabdeckung:

| Message | mab~-Äquivalent | Test-Kategorie |
|---------|----------------|----------------|
| `enable 0/1` | `mab_tilde_enable` (inference_worker:1442-1446) | T5 (Edge-Case) |
| `reload` | Control-Message `reload` (inference_worker:1466-1478) | T5 |
| `dump` | Control-Message `dump` (inference_worker:1494-1496) | T5 |
| `load <path>` | Control-Message `load` (inference_worker:1479-1493) | T5 |
| `method <name>` | Control-Message `method` (inference_worker:1545-1557) | T5 |
| `set <attr> <val>` | Control-Message `set` (inference_worker:1497-1502) | T5 |
| `get <attr>` | Control-Message `get` (inference_worker:1503-1506) | T5 |
| `get_attributes` | Control-Message (inference_worker:1507-1510) | T5 |
| `get_methods` | Control-Message (inference_worker:1511-1516) | T5 |
| `print_available_models` | Control-Message (inference_worker:1517-1530) | T5 |
| `download <card>` | Control-Message (inference_worker:1532-1538) | T5 |
| `delete <card>` | Control-Message (inference_worker:1539-1543) | T5 |
| `gpu 0/1` | Control-Message (inference_worker:1447-1465) | T1/T5 |

### Python-Funktionen für Testing (inference_worker.py)

Reihenfolge wie sie in Tests aufgerufen werden:

```
load_model(path, use_gpu) → (model, device)
    ├── torch.jit.load(resolve_model_path(path), map_location=device)
    └── model.eval()

get_method_params(model) → {method: (ci, ri, co, ro)}
    └── model.<method>_params → Tensor[4] → tuple

compute_layout(method_params, bufsize) → (block_size, max_in, max_out)
    └── max(input_ratio × output_ratio, bufsize) über alle Methoden

infer_method(model, device, method, params, input_block) → numpy array
    ├── 2D input (ci, bs) → forward/encode/decode/prior → 2D output
    └── 3D input (B, ci, bs) → batched forward → 3D output (Phase 6)

detect_model_type(model) → "RAVE" | "AFTER" | "MusicNet" | "TorchScript" | "unknown"
    └── model._c._type().name() → String-Matching

detect_model_attributes(model) → {name: value}  (skalare ≤32 Elemente)
    └── KNOWN_ATTRIBUTE_PATTERNS: sr, sample_rate, latent_size, ...

collect_model_info(model, path) → dict
    ├── method_params, compute_layout, detect_model_type, detect_model_attributes
    └── model_type, methods[], params{}, layout{}, attributes{}, labels{}

query_model(path) → stdout → sys.exit(0)
    └── load → collect_model_info → print_info_block → MAB_INFO_BEGIN/END
```

### RAVE-Methoden-Parameter-Konvention

Jedes RAVE/AFTER-Modell exportiert `{method}_params` als Tensor `[ci, ri, co, ro]`:

| Methode | ci (in) | ri (ratio) | co (out) | ro (ratio) | Semantik |
|---------|---------|------------|----------|------------|----------|
| `forward` | 1 | 1 | 1 | 1 | Audio → Encode → Decode → Audio |
| `encode` | 1 | 1 | latent | block | Audio → Latent |
| `decode` | latent | block | 1 | 1 | Latent → Audio |
| `prior` | 1 | block | latent | block | Conditioning → Latent-Sample |

**Kritisches Detail (infer_method, inference_worker:822-885):**
`decode` und `prior` nehmen NUR das letzte Sample pro Kanal:
```python
# decode: input (ci, bs) → z = input[:, -1:] → model(z) → output
# prior:  input (ci, bs) → z = input[:, -1:] → model(z) → output
```
Das bedeutet: bei einem Block von 2048 Samples wird nur Sample 2048 verwendet.
Die restlichen 2047 Samples werden ignoriert. Der Output wird auf die
angeforderte block_size getrimmt.

### Test-Ausführung (Lokal, ohne Max)

```powershell
# Alle Python-Tests:
.venv\Scripts\python -m pytest test/ -v

# Nur Modell-Lade-Tests:
.venv\Scripts\python -m pytest test/test_model_loading.py -v

# Nur mab.info-Tests:
.venv\Scripts\python -m pytest test/test_mab_info_models.py -v

# Nur Dispatch-Tests:
.venv\Scripts\python -m pytest test/test_infer_all_models.py -v

# GPU-Tests (nur mit CUDA):
.venv\Scripts\python -m pytest test/ -v -k "gpu"

# C++-Tests bauen + ausführen:
cmake --build --preset debug
Get-ChildItem build\Debug\test_*.exe | ForEach-Object { & $_ }
```

### Externe Referenzen

| Quelle | URL | Relevanz |
|--------|-----|----------|
| RAVE GitHub | https://github.com/acids-ircam/rave | Modell-Architektur, --streaming-Export, Configuration-Typen |
| nn_tilde GitHub | https://github.com/acids-ircam/nn_tilde | Paritäts-Referenz: Messages, Attribute, MC/mcs-IO |
| RAVE Pretrained Models | https://acids-ircam.github.io/rave_models_download | Referenz-Modelle für Kompatibilitätstests |
| nn~ Scripting Examples | https://github.com/acids-ircam/nn_tilde/tree/master/scripting | effects.py/features.py/unmix.py → Modell-Typen ohne RAVE-Methoden |
| PyTorch JIT Docs | https://pytorch.org/docs/stable/jit.html | `torch.jit.load()`, `ScriptModule`, `_c.get_methods()` |

