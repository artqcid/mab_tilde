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
    long cores;                 // PyTorch-Inferenz-Threads (1 = Single-Core)
    
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
    long is_mc;                 // 1 = mc.mab~ mode, 0 = mab~ mode
    long channel_map[16];       // per-inlet channel count (MC mode)
    long n_batches;             // fixed output channels from `chans` attribute (0 = auto)
} t_mab_tilde;
```

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
| `mab_info` | MODULE | `mab.info.mxe64` | mab_info.cpp, worker_launch.cpp, max_path_resolve.cpp |
| `test_worker_launch` | EXE | build/Debug/test_worker_launch.exe | test_worker_launch.cpp + worker_launch.cpp |
| 16 weitere Tests | EXE | build/Debug/test_*.exe | Jeweils test/test_*.cpp |

**Phase 5 – Doppelkompilierung:** `mc.mab~.mxe64` wird aus der **gleichen** `mab_tilde.cpp` kompiliert wie `mab~.mxe64`, aber mit `target_compile_definitions(... PRIVATE MC_MAB_TILDE_MODULE)`. Der `#ifdef`-Block in `ext_main` registriert dann nur die `mc.mab~`-Klasse.

**Build-Befehle:**
```powershell
cmake --preset debug          # Konfigurieren
cmake --build --preset debug  # Kompilieren (Output: build/Debug/mab~.mxe64)
```

**Deploy nach Max 9:**
```powershell
Copy-Item build\Debug\mab~.mxe64 "$env:USERPROFILE\Documents\Max 9\Packages\mab_tilde\externals\"
Copy-Item build\Debug\mc.mab~.mxe64 "$env:USERPROFILE\Documents\Max 9\Packages\mab_tilde\externals\"
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
| `CMakeLists.txt` | Build: 3 Libraries + 17 Tests, Native Max SDK (kein min-devkit) | CMake |
| `CMakePresets.json` | CMake-Presets: debug/release, VS 18 2026 x64 | JSON |
| `requirements.txt` | Python-Deps: torch, numpy, mcp, fastmcp, onnxruntime | Text |
| `setup_env.bat` | Windows: venv erstellen + pip install | Batch |
| `.ragignore` | Pfade, die `index_project_code` ausschließt (min-api, build, .venv) | Text |
| `.mcp.json` | MCP-Konfiguration für VS Code / OpenCode | JSON |
| `opencode.json` | OpenCode Agent-Konfiguration (Modelle, Permissions, Compaction) | JSON |

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
