# nn_tilde → mab~ Paritäts-Delta (fehlende Modell-Parameter/-Optionen)

**Referenz-Repo:** `C:\Users\marku\Documents\GitHub\thirdParty\nn_tilde` (lokaler Clone)
**Analysierte Dateien:** `src/frontend/maxmsp/shared/nn_base.h`, `.../nn_tilde/nn_tilde.cpp`,
`.../nn.info/nn.info.cpp`, `.../mc.nn_tilde/mc.nn_tilde.cpp`, `.../mcs.nn_tilde/mcs.nn_tilde.cpp`,
`.../shared/{array,buffer,dict}_tools.h`, `.../shared/max_model_download.h`, `src/shared/model_download.h`,
`src/source/{attributes,buffers,effects,features,unmix}.py`
**Stand:** Verifiziert gegen echten Quellcode. `mab~` = `source/projects/mab_tilde/mab_tilde.cpp` + `inference_worker.py`.

## 1. Argumente (positionale Objekt-Argumente)

nn_tilde (`nn_base.h:419-478`, `mcs.nn_tilde.cpp:171-219`):
| # | Name | Bedeutung |
|---|---|---|
| 1 | `model path` | Pfad zum `.ts`; Download-Ordner wird zuerst geprüft |
| 2 | `method` | Default `"forward"` |
| 3 | `buffer size` | Default 4096; `0` = No-Thread/Low-Latency; `< ratio` wird hochgezogen, sonst `power_ceil` |
| 4 | (nicht deklariert) | Anzahl Inlets, überschreibt Modell-Vorgabe |
| 5 | (nicht deklariert) | Anzahl Outlets |
| — | `"void"` als Arg1 | Void-Modus: Arg2=Inlets, Arg3=Outlets, Arg4=Buffer-Size (reine Zahlen, kein Modell) |
| mcs | Arg3 = `n_batches` | Anzahl Inlets/Outlets (Batch) |

`mab~` aktuell: `model method bufsize gpu num_channels cores` (`mab_tilde.cpp:209-231`).
**Fehlt:** Void-Modus, Inlet-/Outlet-Override (Arg4/5), `n_batches`-Argument, `buffer size 0`-Semantik.

## 2. Messages

nn_tilde (`nn_base.h:197-387`, `nn.info.cpp`) → `mab~`-Status:

| Message | nn_tilde | mab~ |
|---|---|---|
| `method <name>` | validiert via `has_method`, `wait_for_buffer_reset` | ✅ forwarded (ignoriert Folge-Args) |
| `load <path>` / `reload` | als anything-Sub-Commands | ✅ (`reload`/`load` → Prozess-Neustart) |
| `dump` | model_path, Dims, Ratios, Methods, Attributes | ⚠️ nur Konsole-Log, nicht an Worker |
| `print <key> ...` | intern (Buffer-/Download-Progress) | ❌ fehlt |
| `notify` | Buffer-Notifications (`track_buffers`) | ❌ fehlt |
| `print_available_models` | alle ladbaren Modelle | ❌ fehlt |
| `download <card> [name]` | asynchron, IRCAM API, Progress | ❌ fehlt |
| `delete <card>` | löscht `.ts`-Datei | ❌ fehlt |
| `get_attributes` / `get_methods` | anything-Sub-Commands | ❌ fehlt |
| `get <attr>` | `Backend::get_attribute_as_string` | ⚠️ nur Konsole, kein Rückweg |
| `set <attr> <args…>` | `Backend::set_attribute` → wirkt auf Modell | ❌ blockiert (Whitelist) + nie an Worker |

nn.info vs. mab.info: `get_available_models` (Outlet/Dict), `download`, `delete`, `print` → **fehlen** in mab.info.

## 3. Attribute (Max-Attribute)

| Attribut | nn_tilde | mab~ |
|---|---|---|
| `enable` (bool) | direkt gelesen; **Auto-Disable** bei DSP-Vector > Buffer | ⚠️ Message, nur `post` |
| `gpu` (bool) | Setter → `use_gpu()` bei Init (CUDA→MPS→CPU) | ⚠️ nur Logger „requires reload", nie an Worker |
| `track_buffers` (bool, Default false) | Buffer-Tracking via notify | ❌ fehlt |
| `chans` (nur mc./mcs.) | fixe Out-Kanalzahl | ❌ fehlt |
| `dict` (nur nn.info) | Dictionary-Binding | ❌ mab.info hat `out_dict`, kein Binding-Attribut |
| — | mc.: `multichanneloutputs` + `inputchanged` (Max-Methoden) | ❌ fehlt |

## 4. Modell-Attribute-Passthrough — KRITISCH

- **nn_tilde:** `anything` → `set/get` ruft `Backend::set_attribute`/`get_attribute_as_string`
  (`backend.cpp:281-441`): ruft `set_<attr>()`/`get_<attr>()` am Modell; Typ-Hash
  `0=bool 1=int 2=float 3=string 4=tensor 5=buffer`; Python-Registrierung via
  `register_attribute` (`module.py:140-175`), get/set-Callbacks werden automatisch generiert.
  **Werte wirken nachweislich aufs Modell.**
- **mab~:** `set`/`get` (`mab_tilde.cpp:635-672`) sind lokal auf Whitelist begrenzt und werden
  **nicht** an den Worker gereicht; `anything` forwardet Strings; der Worker speichert Attribute
  nur in `RuntimeAttributes.attrs` (Dict + Log, `inference_worker.py:757-766, 1003-1010`) und wendet
  sie **nie** per `setattr` auf das Modell an.

## 5. Buffer~-Handling

- **nn_tilde:** `BufferManager` (`buffer_tools.h`) erzeugt pro Modell-Buffer-Attribut
  (`get_buffer_attributes()`) eine `c74::min::buffer_reference`; `set <attr> <buffer~name>` verlinkt
  sie; Tracking nur bei `track_buffers=true`; interne Namen `"<attr>#<idx>"`; `sr` wird mitgegeben.
  Tensor-Attribute akzeptieren Max-`array`-Namen.
- **mab~:** kein buffer~-Support (0 Treffer für buffer_reference/buffer~ in `source/projects/`).

## 6. Model-Download (IRCAM Forum API)

- **nn_tilde:** API-Root `https://play.forum.ircam.fr/rave-vst-api/`
  (`model_download.h:193-202`), Endpoints `available_models`, `download_model?model=<card>`;
  Download-Pfad `<External>/../../models`, Datei `<name>.ts` bzw. `[optional_name].ts`;
  Lock-Datei gegen Doppel-Download, max. 2 Threads, Progress via `print`; Windows-TLS über
  `cacert.pem`.
- **mab~:** nur im WSAP §2 dokumentiert, **nicht implementiert**.

## 7. mc./mcs.

- **mc.nn~:** `chans`, `channel_map` je Modell-Input, `multichanneloutputs`/`inputchanged`,
  `multichannelsignal`-Inlets/Outlets.
- **mcs.nn~:** `n_batches`, `chans`, `channel_map` mit `n_batches` Einträgen, Batch-Shape-Labels.
- **mab~:** Phase 5/6 offen (nur `num_channels`-Argument + `[num_channels, block_size]`-Layout).

## 8. Undokumentierte Optionen (implementiert, nicht in Help/Maxref)

1. `notify`-Message (Buffer-Notifications)
2. anything-Sub-Commands `reload`/`load`/`get_attributes`/`get_methods`/`get`/`set`
3. Void-Modus + Arg4/5-Overrides (nn~) + Arg3 `n_batches` (mcs)
4. `chans` (mc/mcs)
5. Buffer-Size `0` = No-Thread; **Windows: Thread-Modus hart deaktiviert** (`nn_base.h:518-524, 707-711`, PyTorch-Leak-Bug #24237)
6. Tensor-Attribute (Typ 4) akzeptieren Max-`array`-Namen
7. `download` mit optionalem Namen-Argument
8. Auto-Disable bei DSP-Vector > Buffer; Auto-Bypass solange `can_perform()` false

## 9. Demo-Modell-Attribute (nn_tilde `src/source/*.py`) — Testmodell-Vorlage

| Datei | Attribute |
|---|---|
| `attributes.py` | `attr_int`(0), `attr_float`(0.), `attr_str`("apple"), `attr_enum`("horse", validiert), `attr_bool`(False), `attr_list`(4-getypt) |
| `buffers.py` | `buf` (Buffer, min 64/max 2048 Samples, sr) |
| `effects.py` | `gain_factor`(1.), `polynomial_factors`(4×float), `saturate_mode`(tanh/clip), `invert_signal`(bool), `fractal`(int+float, validiert) |
| `features.py` | (keine Attribute) |
| `unmix.py` | `sr`(44100) |

**Hinweis:** `temperature`, `frequency`, `denoise`, `pitch_shift`, `f0`, `stretch` stehen **nicht**
im nn_tilde-Code — sie stammen aus den jeweiligen Modellen (RAVE/AFTER/vschaos) via
`register_attribute`. Der Passthrough ist komplett generisch.

## Priorisierung (Empfehlung für mab~)

1. **Modell-Attribute-Passthrough** (`set`/`get` → Worker → `setattr` auf Modell, Typ-Hash) — Grundlage für alle „verschiedene Modelle"-Parameter
2. anything-Sub-Commands `get_attributes`/`get_methods`, `dump` an Worker durchreichen
3. `track_buffers` + buffer~-Support (Phase 5-Vorbereitung)
4. `print_available_models`/`download`/`delete` (IRCAM API)
5. `mc.mab~`/`mcs.mab~` (Phase 5/6): `chans`, `channel_map`, `inputchanged`, `n_batches`
