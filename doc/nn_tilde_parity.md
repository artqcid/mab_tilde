# nn_tilde → mab~ Paritäts-Delta

_Referenz: `C:\Users\marku\Documents\GitHub\thirdParty\nn_tilde`. Nur offene Punkte.
Erledigte Features (P1-P6) siehe §4 History. Status-Tracking: `doc/checklist.md`._

---

## 1. Priorisierung (offen)

| # | Punkt | Status | Implementierung |
|---|-------|--------|-----------------|
| P7 | **`track_buffers` + buffer~-Support** | ⚠️ TEILWEISE | Vorbereitung: `buffer_manager.h` + Feld in `t_mab_tilde` ✅; buffer_reference-Anbindung → offen (nach Phase 5) |
| P8 | **`mc.mab~`** (Multichannel) | ✅ FERTIG (Max-verifiziert) | Phase 5: Doppelkompilierung, channel_map (Header v3), `multichanneloutputs`/`inputchanged`, 1-in-1-out MC-IO, `Z_MC_INLETS`, `chans` — Max-Runtime-Test bestanden (checklist 5.8) |
| P9 | **`mcs.mab~`** (Batched MC) | ✅ IMPLEMENTIERT (Max-Test offen) | Phase 6: `n_batches`-Inlets/-Outlets, batch-major SHM `[B×ci×bs]`, batched `infer_method`, `multichanneloutputs`/`inputchanged` pro Batch — Unit-Tests + Build grün, Max-Runtime-Test ausstehend (checklist 6.4) |
| P10 | **Argument-Overrides** (Inlet/Outlet, `n_batches`) | 📋 DOKUMENTIERT | §3: nn_tilde-Codestellen referenziert; Umsetzung → Phase 6 (checklist.md) |
| P11 | **`mab.info`: download/delete/print** | ✅ FERTIG | Worker CLI-Flags + C++ Message-Handler (`mab_info.cpp`) |

---

## 2. P7: Buffer~-Support (Spezifikation)

### nn_tilde-API (buffer_tools.h)

```
BufferManager erzeugt pro Modell-Buffer-Attribut eine buffer_reference.
track_buffers (bool, Default false) aktiviert Buffer-Tracking.
```

**Ablauf:**
1. Modell deklariert Buffer-Attribute via `get_buffer_attributes()` → Liste von `(name, min_samples, max_samples)`
2. `BufferManager` erzeugt `c74::min::buffer_reference` pro Attribut
3. `set <attr> <buffer~name>` verlinkt Attribut mit Max-Buffer~
4. Tracking nur aktiv wenn `track_buffers=true`
5. `notify`-Message sendet Buffer-Updates (Länge, SR, Kanalzahl)
6. Interne Namen: `"<attr>#<idx>"`, Sample-Rate wird mitgegeben
7. Tensor-Attribute (Typ 4) akzeptieren Max-`array`-Namen statt buffer~

### mab~-Implementierung (P7)

**Neue Dateien:**
- `buffer_manager.h` — C++: `buffer_reference`-Wrapper, `track_buffers` Flag, `notify`-Handler
- `inference_worker.py` — Python: Buffer-Daten via SHM bereitstellen

**Neue Messages:**
- `track_buffers <0/1>` — Buffer-Tracking ein/aus (Default: 0)
- `notify` — wird von C++ an Max gesendet bei Buffer-Änderungen
- `print <key>` — Download/Buffer-Progress (intern)

**Neue Attribute:**
- `track_buffers` (bool, Default false) — Max-Attribut

---

## 3. P8/P9/P10: mc./mcs.-Spezifikation

### mc.nn~ (Multichannel)
- `chans <n>` — fixe Output-Kanalzahl
- `channel_map` pro Modell-Input: `[count_inlet0, count_inlet1, ...]`
- `multichanneloutputs` / `inputchanged` — Max-Methoden für MC-Signal-Routing
- `multichannelsignal`-Inlets/Outlets statt `signal`

### mcs.nn~ (Batched Multichannel)
- Wie mc, plus `n_batches` — Anzahl paralleler Inlet/Outlet-Paare
- `channel_map` mit `n_batches` Einträgen
- Batch-Shape-Labels für numpy/torch: `(n_batches, channels, block_size)`

### mab~-Umsetzung (Phase 5/6)
- **P8 ✅:** `mc.mab~` in `ext_main` registriert (Doppelkompilierung via `MC_MAB_TILDE_MODULE`); Shared-Struct mit mab~; `channel_map` in Header v3; `multichanneloutputs`/`inputchanged`/`chans`; MC-IO immer 1-in-1-out mit Kanalzahl über das MC-System (abweichend von nn_tilde's m_model_in Inlets — bewusste Design-Entscheidung, siehe projektwissen.md Phase 5)
- **P9 ✅ (Max-Test offen):** `mcs.mab~` — Dreifach-Kompilierung via `MCS_MAB_TILDE_MODULE`; `mcs_batches` Inlets/Outlets; batch-major SHM-Layout `[n_batches × channels_in × block_size]` (C++ Zeile `b*ci+c`, Python `view(n_batches, ci, bs)`); `infer_method` mit Batched-Forward `(B,ci,bs)`; Arg-Reihenfolge `[model, method, n_batches, bufsize, gpu, cores]`
- **P10:** Arg-Overrides für Inlet/Outlet-Anzahl + `n_batches`

### P10 – Argument-Overrides: konkrete nn_tilde-Codestellen

**Inlet-/Outlet-Overrides (nn_base.h `init_inputs_and_outputs()`):**
- `nn_base.h:419-478` — gesamte Argument-Parsing-Logik (`init_inputs_and_outputs`)
- `nn_base.h:438-448` — **void-Modus**: `args[0]=="void"`, `args[1]=inlets`, `args[2]=outlets`, `args[3]=bufsize` (nur setzen wenn `>= 1`); Default `n_outlets = 1` falls `-1`
- `nn_base.h:454-467` — **Modell-Modus**: `args[1]=method`, `args[2]=bufsize`, `args[3]=inlets`-Override, `args[4]=outlets`-Override (nur wenn `>= 1`, sonst Layout aus dem Modell)
- `nn_base.h:474-476` — Fehlerpfad: wenn `n_inlets == -1 || n_outlets == -1` → `error("could not initialise object")`
- `nn_base.h:529` — Konstruktor-Init: `n_inlets(-1), n_outlets(-1), n_batches(1)` → `-1` bedeutet "aus Modell-Layout ableiten"

**`n_batches`-Override (mcs.nn_tilde.cpp Konstruktor):**
- `mcs.nn_tilde.cpp:189-197` — **void-Modus**: `args[1]=n_batches`, `args[2]=bufsize`, `channel_map = vector(n_batches, 1)`
- `mcs.nn_tilde.cpp:198-208` — **Modell-Modus**: `args[1]=method`, `args[2]=n_batches`, `args[3]=bufsize`, `channel_map = vector(n_batches, 1)`
- `mcs.nn_tilde.cpp:236-259` — `init_inlets_and_outlets()`: `n_inlets = n_outlets = n_batches`, `multichannelsignal`-Inlets/Outlets
- `mcs.nn_tilde.cpp:221-233` — `update_channel_map(index, count)`: pro Batch-Inlet, `wait_for_buffer_reset` bei Änderung
- `mc.nn_tilde.cpp:101-156` — `get_batches()`: Batch-Anzahl aus Modell-Labels/Args

**Hinweis Layout-Konflikt:** mab~ nutzt aktuell eine eigene Arg-Reihenfolge
(`mab_tilde.cpp:310-333`: `argv[3]=gpu`, `argv[4]=num_channels`, `argv[5]=cores`),
nn_tilde nutzt `args[3]=inlets`/`args[4]=outlets`. P10 muss diese Reihenfolge
mit nn_tilde angleichen (siehe checklist.md).

---

## 4. Bereits umgesetzt (P1–P6, Phase 4.6)

| # | Feature | Code |
|---|---------|------|
| P1 | Modell-Attribute-Passthrough (`set`/`get` → Worker → Modell) | `inference_worker.py:_apply_model_attribute` |
| P2 | anything-Sub-Commands, `dump` | `mab_tilde.cpp:mab_tilde_anything` |
| P3 | `gpu` als echter Setter (Device-Wechsel + Reload) | `mab_tilde.cpp:mab_tilde_gpu` |
| P4 | `buffer size 0` = Auto-Layout (`block_size = max(ratios)`) | `inference_worker.py:compute_layout` |
| P5 | Void-Modus (`mab~ void <in> <out> <bufsize>`) | `mab_tilde.cpp:259-287` |
| P6 | `print_available_models`/`download`/`delete` (IRCAM API) | `inference_worker.py:_remote_available_models` |

**Weitere erledigte Parity-Punkte:**
- Method-Aware IO (Header v2/v3, `encode`/`decode`/`forward`/`prior`)
- `mc.mab~` Multichannel (P8, Header v3 mit `channel_map`)
- `mab.info` Query-Modus (5 Outlets, Dictionary)
- Model-Download mit optionalem `name`-Argument
- `reload`/`load` → Worker-Neustart
- Typ-Koerzierung bool/int/float/str für `set`
- Runtime-Attribute re-applied nach Reload

---

## 5. nn_tilde-Referenz (nur offene Punkte)

### Messages (nn_base.h, nn.info.cpp)

| Message | nn_tilde | mab~-Status |
|---------|----------|-------------|
| `print <key>` | Buffer-/Download-Progress | ❌ → P7 |
| `notify` | Buffer-Notifications | ❌ → P7 |
| `download`/`delete`/`print` via `mab.info` | nn.info leitet durch | ✅ P11 (`mab_info.cpp` Handler + Worker `--download/--delete/--list`) |

### Max-Attribute (nn_tilde → mab~)

| Attribut | nn_tilde | mab~-Status |
|----------|----------|-------------|
| `track_buffers` | Buffer-Tracking via notify | ❌ → P7 |
| `chans` | mc./mcs.: fixe Out-Kanalzahl | ✅ P8 (`mc_mab_tilde_chans` → `n_batches`) |
| `multichanneloutputs` + `inputchanged` | mc.: MC-Signal-Methoden | ✅ P8 (`mab_tilde.cpp:1317`/`1327`) |

### Undokumentierte nn_tilde-Optionen (noch offen)

1. `notify` / `print` → P7
2. Inlet-/Outlet-Overrides (Arg4/5) → P10
3. `chans` (mc) → ✅ P8; `chans` (mcs) → P9
4. Tensor-Attribute (Typ 4) via Max-`array` → P7
5. Auto-Disable bei DSP-Vector > Buffer → nicht priorisiert

### Demo-Modell-Attribute (Test-Vorlage)

nn_tilde `src/source/{attributes,buffers,effects,features,unmix}.py`.
Dokumentiert in `doc/projektwissen.md` unter "Konstanten" und `inference_worker.py` Tests.