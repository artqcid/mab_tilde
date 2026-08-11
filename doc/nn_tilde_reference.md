# nn_tilde Referenz – Strukturen & APIs für mab~-Entwicklung

_Extrahiert aus `C:\Users\marku\Documents\GitHub\thirdParty\nn_tilde`. Nur für P7–P10 relevante Patterns. Quellcode-Verweise mit exakten Dateipfaden und Zeilennummern._

---

## 1. nn_base – Basisklasse (nn_base.h)

**Datei:** `src/frontend/maxmsp/shared/nn_base.h` (827 Zeilen)
**CRTP-Template:** `template <typename nn_name, typename op_type> class nn_base : public object<nn_name>, public op_type`

### 1.1 Member-Variablen (nn_base.h:73-137)

```cpp
// INLETS OUTLETS
std::vector<std::unique_ptr<inlet<>>> m_inlets;     // nn_base.h:73
std::vector<std::unique_ptr<outlet<>>> m_outlets;    // nn_base.h:74

// BACKEND
std::unique_ptr<Backend> m_model;                     // nn_base.h:99
bool m_is_backend_init = false;                       // nn_base.h:100
bool m_ready = false;                                 // nn_base.h:101
std::string m_method;                                 // nn_base.h:102
std::vector<std::string> settable_attributes;         // nn_base.h:103

// IO-Dimensionen
int n_inlets, n_outlets;                              // nn_base.h:105
int m_model_in, m_model_out;                          // nn_base.h:105
int m_in_ratio, m_out_ratio, m_higher_ratio;          // nn_base.h:105
int n_batches;                                        // nn_base.h:105 (Default 1 in nn_base)

// BUFFER
BufferManager m_buffer_manager;                       // nn_base.h:126
int m_buffer_size;                                    // nn_base.h:129
int m_buffer_in, m_buffer_out;                        // nn_base.h:130
std::unique_ptr<circular_buffer<double,float>[]> m_in_buffer;   // nn_base.h:131
std::unique_ptr<circular_buffer<float,double>[]> m_out_buffer;  // nn_base.h:132
std::vector<std::unique_ptr<float[]>> m_in_model, m_out_model;  // nn_base.h:133

// THREADING
bool m_force_refresh, m_use_thread, m_should_stop_perform_thread; // nn_base.h:136
std::binary_semaphore m_data_available_lock;          // nn_base.h:137
std::binary_semaphore m_result_available_lock;        // nn_base.h:137
std::unique_ptr<std::thread> m_compute_thread;        // nn_base.h:138

// DOWNLOAD
std::unique_ptr<MaxModelDownloader> m_downloader;     // nn_base.h:154
```

### 1.2 Init-Flow (nn_base.h:83-95)

```
init_external(args)
  ├── init_model()              // Backend laden, m_model->is_loaded()
  ├── init_downloader()         // MaxModelDownloader
  ├── if args: init_inputs_and_outputs(args)  // Arg-Parsing → n_inlets, n_outlets, m_buffer_size
  ├── init_inlets_and_outlets()               // m_inlets/m_outlets Vektoren befüllen
  ├── init_buffers() (oder später)
  └── init_process()            // Compute-Thread starten (nur single-channel)
```

### 1.3 Arg-Parsing: `init_inputs_and_outputs` (nn_base.h:419-478)

#### Void-Modus: `nn~ void <inlets> <outlets> <bufsize>`

| Arg-Index | Bedeutung | Code |
|-----------|-----------|------|
| args[0]   | `"void"` | nn_base.h:424 |
| args[1]   | `n_inlets` (>= 1) | nn_base.h:439-441 |
| args[2]   | `n_outlets` (>= 1, default 1) | nn_base.h:443-445 |
| args[3]   | `m_buffer_size` | nn_base.h:447 |

#### Modell-Modus: `nn~ <model.ts> <method> <bufsize> <inlets> <outlets>`

| Arg-Index | Bedeutung | Code |
|-----------|-----------|------|
| args[0]   | Modell-Pfad (`.ts`) | nn_base.h:423 |
| args[1]   | `m_method` (z.B. `"forward"`) | nn_base.h:455 |
| args[2]   | `m_buffer_size` | nn_base.h:458 |
| args[3]   | **`n_inlets`-Override** (>= 1, sonst aus Modell-Layout) | nn_base.h:461-463 |
| args[4]   | **`n_outlets`-Override** (>= 1, sonst aus Modell-Layout) | nn_base.h:465-467 |

**Wichtig:** `n_inlets`/`n_outlets` sind mit `-1` initialisiert (nn_base.h Konstruktor: `n_inlets(-1), n_outlets(-1)`).
Nur wenn der Override `>= 1` ist, wird der Wert gesetzt; sonst bleibt `-1` und wird später aus dem
Modell-Layout abgeleitet. Nach `load_model()` wird geprüft: `if ((n_inlets == -1) || (n_outlets == -1))` → `error()`.

### 1.4 Inlet/Outlet-Erstellung: `init_inlets_and_outlets` (nn_base.h:481-530)

```cpp
for (int i(0); i < n_inlets; i++) {
    m_inlets.push_back(std::make_unique<inlet<>>(this, label, "signal"));
}
for (int i(0); i < n_outlets; i++) {
    m_outlets.push_back(std::make_unique<outlet<>>(this, label, "signal"));
}
```

---

## 2. Arg-Reihenfolge: nn_tilde vs. mab~ (KONFLIKT)

| Arg | nn_tilde | mab~ aktuell | P10-Ziel |
|-----|----------|-------------|----------|
| 0   | model path / `"void"` | model path / `"void"` | ✅ identisch |
| 1   | method              | method              | ✅ identisch |
| 2   | buffer_size         | buffer_size         | ✅ identisch |
| 3   | **n_inlets override** | `gpu` (0/1)      | ⚠️ KONFLIKT – P10 muss verschieben |
| 4   | **n_outlets override** | `num_channels`   | ⚠️ KONFLIKT |
| 5   | —                    | `cores`            | ⚠️ KONFLIKT |

**mab~ Status (mab_tilde.cpp:260-267):**
```cpp
if (argc >= 3 && !void_mode) x->buffer_size = atom_getlong(argv + 2);   // ✅ identisch
if (argc >= 4 && !void_mode) x->gpu = atom_getlong(argv + 3);           // ❌ nn_tilde: n_inlets
if (argc >= 5 && !void_mode) x->num_channels = atom_getlong(argv + 4);  // ❌ nn_tilde: n_outlets
if (argc >= 6 && !void_mode) x->cores = atom_getlong(argv + 5);         // ❌ nn_tilde: kein Arg
```

**P10-Plan:** `gpu`, `num_channels`, `cores` als Max-Attribute (nicht als Konstruktor-Args) handhaben.
Args[3]=inlets, args[4]=outlets für nn_tilde-Kompatibilität.

---

## 3. BufferManager – P7 (buffer_tools.h)

**Datei:** `src/frontend/maxmsp/shared/buffer_tools.h` (262 Zeilen)

### 3.1 Klasse & Member

```cpp
class BufferManager {
    std::vector<std::unique_ptr<c74::min::buffer_reference>> m_max_buffers;  // buffer_tools.h:9
    std::vector<std::string> buffer_attributes;                               // buffer_tools.h:10
    bool buffer_track = false;                                                // buffer_tools.h:11
};
```

### 3.2 Methoden-API

| Methode | Signatur | Zeile | Zweck |
|---------|----------|-------|-------|
| `init_buffer_list` | `(Backend*, object_base*)` | 231 | Holt `backend->get_buffer_attributes()`, erzeugt `buffer_reference` pro Attribut |
| `link_attribute_to_buffer` | `(string name, symbol target)` | 63 | Verknüpft Attribut mit Max buffer~-Objekt |
| `set_buffer_tracking` | `(bool)` | 22 | Aktiviert/deaktiviert Tracking |
| `bind_buffer_attribute` | `(Backend*, string, object_base*)` → int | 127 | Bindet Buffer (nur wenn `buffer_track=true`) |
| `unbind_buffer_attribute` | `(Backend*, string, object_base*)` → int | 156 | Entbindet Buffer |
| `modify_buffer_attribute` | `(Backend*, string, object_base*)` → int | 180 | Aktualisiert Buffer-Inhalt |
| `get_notification_callback` | `(string, object_base*, Backend*)` → function | 208 | Callback für `buffer_reference`-Notifications (`"binding"`/`"unbinding"`/`"modified"`) |
| `static_buffer_from_max_buffer` | `<T>(buffer_reference*)` → StaticBuffer<T> | 108 | Konvertiert Max buffer~ → `StaticBuffer` (Kanäle, Samples, SR) |
| `static_buffer_from_name` | `<T>(string)` → StaticBuffer<T> | 88 | Holt Buffer über Attribut-Namen |

### 3.3 nn_base-Integration

```cpp
// nn_base-Instanz hat:
BufferManager m_buffer_manager;       // nn_base.h:126

// Getrackt via Max-Attribut:
attribute<bool> track_buffers{this, "track_buffers", false,  // nn_base.h:181-192
    setter{MIN_FUNCTION{
        m_buffer_manager.set_buffer_tracking(args[0]);
        return args;
    }}};
```

### 3.4 Buffer~-Workflow (nn_tilde)

```
1. Modell deklariert Buffer via backend->get_buffer_attributes()
2. BufferManager::init_buffer_list() → buffer_reference pro Attribut
3. track_buffers = true → Notifications werden aktiv
4. set <attr> <buffer~name> → link_attribute_to_buffer()
5. User modifiziert buffer~ → notification callback → bind/unbind/modify
6. mab~ müsste: Buffer-Daten via SHM an Python weiterreichen
```

**mab~ P7-Unterschied zu nn_tilde:**
- nn_tilde: In-Process (gleicher Thread), `buffer_reference` direkt
- mab~: Process-Isolation (SHM), muss `buffer_reference`-Daten via IPC an Python senden
- mab~ hat Vorbereitung in `buffer_manager.h` (BufferRef/BufferManager C++-Platzhalter)
- nn_tilde Buffer-Typen: Audio-Buffer (`buffer_reference`) + Tensor-Attribute (`array`)

---

## 4. mc.nn~ – Multichannel (mc.nn_tilde.cpp)

**Datei:** `src/frontend/maxmsp/mc.nn_tilde/mc.nn_tilde.cpp` (373 Zeilen)
**Klasse:** `mc_nn : public nn_base<mc_nn, mc_operator<>>`

### 4.1 Zusätzliche Member

```cpp
std::vector<int> channel_map;      // mc.nn_tilde.cpp:100 – [count_inlet0, count_inlet1, ...]
int n_batches_arg = 0;              // mc.nn_tilde.cpp:101 – chans-Attribut-Wert
```

### 4.2 Multichannel-Methoden (Max-SDK)

```cpp
// mc.nn_tilde.cpp:119-123 – in maxclass_setup registriert:
class_addmethod(c, (method)simplemc_multichanneloutputs, "multichanneloutputs", A_CANT, 0);
class_addmethod(c, (method)simplemc_inputchanged, "inputchanged", A_CANT, 0);
```

### 4.3 chans-Attribut

```cpp
attribute<int> chans_attr{this, "chans", 0,  // mc.nn_tilde.cpp:127-143
    setter{MIN_FUNCTION{
        if (args[0] > 0) n_batches_arg = args[0];
        return args;
    }}};
```

### 4.4 channel_map & get_batches

```cpp
int mc_nn::get_batches() {                         // mc.nn_tilde.cpp:146-152
    if (channel_map.size() > 0)
        return *std::max_element(channel_map.begin(), channel_map.end());
    return 1;
}
int mc_nn::get_batches_out() {                     // mc.nn_tilde.cpp:154-160
    if (n_batches_arg > 0) return n_batches_arg;   // chans-Override
    return get_batches();
}
```

### 4.5 init_inlets_and_outlets (Multichannel)

```cpp
// mc.nn_tilde.cpp:168-200
// Inlets: "multichannelsignal" statt "signal"
m_inlets.push_back(std::make_unique<inlet<>>(this, label, "multichannelsignal"));

// Outlets: "multichannelsignal", count = get_batches_out()
outlet<>>(this, label, "multichannelsignal"));
```

### 4.6 init_inputs_and_outputs (ruft nn_base auf, dann channel_map)

```cpp
void mc_nn::init_inputs_and_outputs(const atoms& args) {  // mc.nn_tilde.cpp:162-166
    nn_base::init_inputs_and_outputs(args);                 // Basis-Parsing!
    for (int i(0); i < m_model_in; i++)
        channel_map.push_back(1);                           // Default: 1ch pro Inlet
}
```

---

## 5. mcs.nn~ – Batched Multichannel (mcs.nn_tilde.cpp)

**Datei:** `src/frontend/maxmsp/mcs.nn_tilde/mcs.nn_tilde.cpp` (494 Zeilen)
**Klasse:** `mcs_nn : public nn_base<mcs_nn, mc_operator<>>`

### 5.1 Zusätzliche Member

```cpp
std::vector<long> channel_map;   // mcs.nn_tilde.cpp:197/208 – vector(n_batches, 1)
int n_batches;                   // geerbt von nn_base (nn_base.h:105)
int m_out_channels;              // mcs.nn_tilde.cpp:113
```

### 5.2 Arg-Parsing-Override (mcs.nn_tilde.cpp:162-218)

#### Void-Modus: `mcs.nn~ void <n_batches> <bufsize>`

| Arg | Bedeutung | Code |
|-----|-----------|------|
| args[0] | `"void"` | mcs.nn_tilde.cpp:172 |
| args[1] | **`n_batches`** | mcs.nn_tilde.cpp:192 |
| args[2] | `m_buffer_size` | mcs.nn_tilde.cpp:195 |

#### Modell-Modus: `mcs.nn~ <model.ts> <method> <n_batches> <bufsize>`

| Arg | Bedeutung | Code |
|-----|-----------|------|
| args[0] | Modell-Pfad | mcs.nn_tilde.cpp:172 |
| args[1] | `m_method` | mcs.nn_tilde.cpp:200 |
| args[2] | **`n_batches`** | mcs.nn_tilde.cpp:203 |
| args[3] | `m_buffer_size` | mcs.nn_tilde.cpp:206 |

**Beachte:** mcs.nn~ überschreibt `init_inputs_and_outputs` KOMPLETT (ruft NICHT `nn_base::init_inputs_and_outputs` auf).
`channel_map = std::vector<long>(n_batches, 1)` wird immer gesetzt.

### 5.3 update_channel_map

```cpp
bool mcs_nn::update_channel_map(const long& index, const long& count) {  // mcs.nn_tilde.cpp:221-233
    if (channel_map[index] != count) {
        channel_map[index] = count;
        wait_for_buffer_reset = true;
        return (count == m_model_in);  // true wenn korrekte Kanalzahl
    }
    return true;
}
```

### 5.4 init_inlets_and_outlets (Batched)

```cpp
// mcs.nn_tilde.cpp:236-259
// n_inlets = n_outlets = n_batches
// Inlets/Outlets tragen "multichannelsignal"-Typ
// Pro Batch ein Inlet + ein Outlet
```

---

## 6. nn_tilde Python-Modellstruktur

**Datei:** `src/source/attributes.py` (55 Zeilen) – Vorlage für mab~-Testmodelle

```python
import nn_tilde  # nn_tilde.Module, register_attribute, register_method

class AttributeFoo(nn_tilde.Module):
    def __init__(self):
        super().__init__()
        self.register_attribute("attr_int", 0)
        self.register_attribute("attr_float", 0.)
        self.register_attribute("attr_str", "apple")
        self.register_attribute("attr_enum", "horse")
        self.register_attribute("attr_bool", False)
        self.register_attribute("attr_list", [0, "christophe", 1., True])
        self.register_method("forward", in_chan=1, out_chan=1,
                             in_ratio=2, out_ratio=1, test_method=False)
        self.finish()

    @torch.jit.export
    def set_attr_enum(self, animal: str) -> int:
        # Custom Setter: return 0 = akzeptiert, -1 = abgelehnt
        if animal not in self._valid_animals_:
            return -1
        self.attr_enum = (animal,)   # Tuple-Zuweisung!
        return 0

    @torch.jit.export
    def forward(self, x: torch.Tensor):
        x = torch.zeros(x.shape[:-2] + (2, x.shape[-1]))
        x[..., 0, :] = self.attr_int[0]    # Attribute als Tuple!
        x[..., 1, :] = self.attr_float[0]
        return x

# Export: model.export_to_ts('models/demo_attributes.ts')
```

**Weitere Demo-Modelle:** `buffers.py`, `effects.py`, `features.py`, `unmix.py` – alle folgen dem gleichen Pattern.

---

## 7. Threading-Modell (nn_tilde vs. mab~)

| Aspekt | nn_tilde | mab~ |
|--------|----------|------|
| Architektur | Single-Process, Thread-basiert | Multi-Process, IPC-basiert |
| Audio-Thread | `operator()` → `perform()` oder `model_perform_async` | `mab_tilde_perform64` (block_accumulator) |
| Compute-Thread | `std::thread` + `binary_semaphore` (optional, `m_use_thread`) | Python Worker (eigener Prozess) |
| Synchronisation | `m_data_available_lock` / `m_result_available_lock` | Named Events + Shared Memory Atomics |
| Modell-Inferenz | Direkter `m_model->perform()` Aufruf | IPC: SHM + Event → `infer_method()` |
| Buffer-Access | In-Process `buffer_reference` | Via SHM (muss P7 noch implementieren) |

---

## 8. Mapping: nn_tilde → mab~ (Implementierungs-Guide)

| nn_tilde Konzept | nn_tilde Datei:Zeile | mab~ Äquivalent | Status |
|-----------------|---------------------|-----------------|--------|
| `nn_base::init_inputs_and_outputs` | nn_base.h:419-478 | `mab_tilde_new` Arg-Parsing (mab_tilde.cpp:240-287) | ⚠️ P10: Arg-Reihenfolge anpassen |
| `n_inlets`/`n_outlets` Override | nn_base.h:461-467 | `x->channels_in`/`x->channels_out` (mab_tilde.cpp:43-48) | ⚠️ P10: aus Args[3]/[4] lesen |
| `BufferManager::init_buffer_list` | buffer_tools.h:231-252 | `buffer_manager.h` (Platzhalter) + SHM-Transfer | ❌ P7 |
| `track_buffers` | nn_base.h:181-192 | `x->buffer_mgr` Feld + Max-Attribut | ❌ P7 |
| `mc_nn::channel_map` | mc.nn_tilde.cpp:100 | Neues Feld in `t_mab_tilde` | ❌ P8/P9 |
| `mc_nn::get_batches` | mc.nn_tilde.cpp:146-152 | `channel_map` Max-Element | ❌ P8/P9 |
| `chans`-Attribut | mc.nn_tilde.cpp:127-143 | `n_batches_arg` / fixe Out-Kanalzahl | ❌ P8 |
| `multichanneloutputs`/`inputchanged` | mc.nn_tilde.cpp:119-123 | `class_addmethod` in `ext_main` | ❌ P8 |
| `mcs_nn::n_batches` | mcs.nn_tilde.cpp:192/203 | `x->n_batches` Feld | ❌ P9/P10 |
| `mcs_nn::init_inlets_and_outlets` | mcs.nn_tilde.cpp:236-259 | `n_inlets = n_outlets = n_batches` | ❌ P9 |
| `mcs_nn::update_channel_map` | mcs.nn_tilde.cpp:221-233 | Analoge Funktion für mab~ | ❌ P9 |
