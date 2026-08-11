# mab~ Teststrategie – Offline/CI-Tests ohne Max Runtime

_Stand: 2026-08-11 (Klarstellung Python-vs-Max-Tests). Erstellt von Architect nach Analyse aller 20 Dateien (19 TorchScript + 1 ONNX) in D:\AI-Models\ts models`, der bestehenden C++-Tests (19), Python-Tests (124)
und der drei External-Architekturen (mab~, mc.mab~, mcs.mab~)._

---

## 1. Zielsetzung

Diese Teststrategie definiert, welche Tests **ohne** Max Runtime durchführbar
sind – d.h. direkt via `pytest` und C++-Unit-Test-EXEs. Ziel ist:

1. **Vollständige Modell-Kompatibilität** prüfen: Werden alle 19 TorchScript-Modelle im
   Modell-Ordner korrekt geladen? Liefert `mab.info` die richtigen Infos?
2. **Methoden-Dispatch verifizieren**: Stehen alle Methoden (forward, encode,
   decode, prior) mit korrekten Parameter-Layouts zur Verfügung?
3. **CPU/GPU-Loading**: Können Modelle sowohl auf CPU als auch auf GPU (CUDA)
   geladen werden?
4. **Soundverarbeitung** (als Python-Integrationstest): Werden die Audiosignale
   korrekt (sample-genau) verarbeitet?
5. **Regression-Safety**: Jedes Modell im Ordner als Test-Case.
6. **Audio-Qualität + Performance** (reines Python): Signalverarbeitung
   blockweise via infer_method() direkt in Python testen — CPU und GPU.
   Kein Max, kein Shared Memory, kein C++-DSP nötig.

Tests, die **zwingend Max Runtime** benötigen (Shared Memory IPC mit C++,
DSP-Perform, IO-Rebuild via Qelem, Crash-Monitor, ASIO-echtzeit-Scheduling),
werden separat als Max-Runtime-Tests klassifiziert und sind nicht Teil
dieses Dokuments.

**Faustregel:** Alles, was infer_method() aufruft, funktioniert standalone in
Python. Nur SHM-Handshake, Ringbuffer-Latenz und DSP-Tick-Timing brauchen Max.

---

## 2. Modell-Inventar (19 TorchScript + 1 ONNX)

| Modell | Größe | Methoden (via inspect) | Latent | Block-Size |
|--------|-------|------------------------|--------|------------|
| `darbouka_onnx.ts` | 25 MB | **AUSGESCHLOSSEN** (ONNX, kein TorchScript) | – | – |
| `afterv2.audio.instr.ts` | 219 MB | **AUSGESCHLOSSEN** (RAM >10 GB, nicht testbar auf 16 GB) | – | – |
| `demo_attributes.ts` | 8 KB | forward | – | 512 |
| `demo_buffers.ts` | 11 KB | unbekannt | – | ? |
| `demo_mc.ts` | 5 KB | unbekannt | – | ? |
| `effects.ts` | 11 KB | unbekannt | – | ? |
| `features.ts` | 0.2 MB | unbekannt (hop=256) | ? | 256 |
| `modell_30min_27915e19b0.ts` | 1.8 MB | unbekannt | ? | ? |
| `musicnet.ts` | 237 MB | encode, decode, forward | 16 | 2048 |
| `nasa.ts` | 159 MB | unbekannt | ? | ? |
| `thirdModelTest3000Epoche.ts` | 49 MB | unbekannt | ? | ? |
| `vintage.ts` | 460 MB | encode, decode, forward | ? | ? |
| `voice_hifitts_b2048_r48000_z16.ts` | 164 MB | unbekannt (z=16) | 16 | 2048 |
| `voice_jvs_b2048_r44100_z16.ts` | 149 MB | unbekannt (z=16) | 16 | 2048 |
| `voice_vctk_b2048_r44100_z22.ts` | 149 MB | unbekannt (z=22) | 22 | 2048 |
| `voice_vocalset_b2048_r48000_z16.ts` | 164 MB | unbekannt (z=16) | 16 | 2048 |
| `voice-multi-b2048-r48000-z11.ts` | 150 MB | encode, decode, forward | 11 | 2048 |
| `water_pondbrain_b2048_r48000_z16.ts` | 121 MB | unbekannt (z=16) | 16 | 2048 |
| `wavetable.ts` | 7 KB | forward | – | ? |
| `wheel.ts` | 160 MB | unbekannt | ? | ? |

**Legende:** `z=N` = Dateiname enthält `_z<N>` (latent_size vermutet).

---

## 3. Test-Kategorien (ohne Max Runtime)

### Kategorie A – Unit-Tests (existiert, erweiterbar)

Diese Tests existieren bereits und benötigen keine echten Modelle:

| Test-Datei | Prüft | Status |
|------------|-------|--------|
| `test/test_method_layout.py` `class TestInferMethodSemantics` | dispatch mit Fake-Modell (119) | ✅ |
| `test/test_method_layout.py` `class TestComputeLayout` | Layout-Berechnung (5) | ✅ |
| `test/test_method_layout.py` `class TestInferMethodBatched` | batched infer (5) | ✅ |
| `test/test_query_mode.py` | collect_model_info, print_info_block (6) | ✅ |
| `test/test_attribute_passthrough.py` | _coerce_value, RuntimeAttributes (11) | ✅ |
| `test/test_python_shared_memory.py` | Header-Layout, Puffer-Berechnung | ✅ |
| `test/test_block_size_extraction.py` | SharedMemoryHeader-Offset-Validierung | ✅ |
| `test/test_shared_memory_v2.py` | Header v3 + apply_method (7) | ✅ |

### Kategorie B – Modell-Lade-Tests (NEU, 19 TorchScript-Modelle)

**Ziel:** Jedes Modell im `D:\AI-Models\ts models`-Ordner laden → Methoden
extrahieren → Layout berechnen – auf CPU UND GPU.

**Datei:** `test/test_model_loading.py` (neu)

| Testklasse | Tests | Zeit |
|------------|-------|------|
| `TestModelLoadingAll` | 19× `test_load_cpu_<name>` → load_model + eval | ~2-5 min CPU |
| `TestModelLoadingAll` | 19× `test_load_gpu_<name>` → load_model(gpu=True) + eval | ~2-5 min GPU |
| `TestModelLayoutAll` | 19× `test_layout_<name>` → `get_method_params` + `compute_layout` + Shapes | <1 s |

**GPU-Tests sind `skipIf(not torch.cuda.is_available())` – laufen nur bei
CUDA-fähiger Hardware.**

### Kategorie C – mab.info-Integrationstests (NEU)

**Ziel:** `query_model()` für jedes Modell aufrufen → Ausgabe parsen → gegen
erwartete Felder prüfen.

**Datei:** `test/test_mab_info_models.py` (neu)

| Testklasse | Tests | Prüft |
|------------|-------|-------|
| `TestQueryAllModels` | 19× → `query_model()` aufrufen | MAB_INFO_BEGIN/END, Modell-Typ, Methoden-Liste, Parameter |
| `TestInfoBlockStructure` | 19× → Ausgabe parsen | model_path, model_type, block_size, channels_in/out, latent_size, methods, params |
| `TestInfoDictJson` | 19× → MABJSON-Block validieren | gültiges JSON |

### Kategorie D – Methoden-Dispatch-Integrationstests (NEU)

**Ziel:** `infer_method()` mit echten Modellen aufrufen → Output-Shapes +
Inhalte prüfen (NaN/Inf-Prüfung). Jede Methode eines Modells.

**Datei:** `test/test_infer_all_models.py` (neu)

| Testklasse | Tests | Prüft |
|------------|-------|-------|
| `TestInferAllMethods` | 1× pro Methode pro Modell (~50 Tests) | Output-Shape korrekt, keine NaN/Inf |
| `TestInferRandInput` | 1× pro Modell für `forward` | forward gibt gültigen Output bei Zufalls-Input |
| `TestInferDeterministic` | 1× pro `forward`-Modell | gleicher Input → gleicher Output (keine Dropout-Seiteneffekte) |

### Kategorie E – Audio-Performance-Tests (NEU, reines Python, kein Max nötig)

**Ziel:** Audio-Signalverarbeitung mit echten Modellen prüfen:
- Passthrough-Konsistenz (forward sollte Signal annähernd erhalten)
- encode→decode Roundtrip (klangliche Konsistenz)
- Audio-Leistungs-Benchmark

**Datei:** `test/test_audio_quality.py` (neu)


**Umgebung:** Reines Python — `infer_method()` aus `inference_worker.py` direkt
aufrufen. Blockweises Processing von .wav-Dateien (via `soundfile`/`scipy`).
Laeuft auf CPU und GPU (`device`-Parameter). Kein Max, kein ASIO-Treiber, kein
Shared-Memory-Handshake noetig. Misst echte Modell-Inferenzzeit, nicht IPC-Latenz.

| Testklasse | Tests | Prüft |
|------------|-------|-------|
| `TestForwardPassthrough` | 1× pro forward-fähiges Modell | Input ≈ Output (Korrelation > 0.9 oder SNR > 20dB) |
| `TestEncodeDecodeRoundtrip` | 1× pro encode+decode-fähiges Modell | Rekonstruktion hat plausible Qualität |
| `TestSilenceThroughput` | 1× pro Modell | Silence in → Silence out (kein DC-Offset, keine Artefakte) |
| `TestBenchmark` | 1× pro Modell | ms pro Block (für Performance-Datenblatt) |

### Kategorie F – Edge-Case- und Stress-Tests (NEU)

**Datei:** `test/test_model_edge_cases.py` (neu)

| Testklasse | Tests | Prüft |
|------------|-------|-------|
| `TestLoadUnloadCycles` | `musicnet.ts` 10× laden/entladen | Memory-Leak, kein Crash |
| `TestConcurrentModels` | 2 verschiedene Modelle gleichzeitig | Threading-Sicherheit |
| `TestLargeBlockSize` | bufsize=4096 mit `musicnet.ts` | MAX_BLOCK_SIZE-Grenze |
| `TestSmallBlockSize` | bufsize=64 mit `musicnet.ts` | kein Crash bei sehr kleinen Blöcken |
| `TestMaxBlockBoundary` | bufsize=0, bufsize=8192 | Fehlerbehandlung |
| `TestMissingMethod` | `infer_method` mit unbekannter Methode | graceful error |
| `TestRaveAttributes` | `demo_attributes.ts` set/get aller Attribute | nn_tilde-Parity |
| `TestNullInput` | Null-Tensor als Input | kein Segfault |

---

## 4. Implementierungshinweise

### 4.1 Test-Framework-Konventionen

Alle neuen Python-Tests folgen dem bestehenden Muster (vgl. `test/test_method_layout.py`):

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
import unittest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from inference_worker import load_model, get_method_params, infer_method, collect_model_info

MODEL_DIR = r"D:\AI-Models\ts models"

@unittest.skipUnless(os.path.exists(MODEL_DIR),
                     "Model directory not found: D:\\AI-Models\\ts models")
class TestXxx(unittest.TestCase):
    ...

if __name__ == '__main__':
    unittest.main()
```

### 4.2 Parametrisierte Modell-Tests

Statt 20 separate Testmethoden zu schreiben → dynamische Testfall-Generierung:

```python
import glob

def model_test_cases():
    """(Directory, filename) tuples for all .ts models."""
    files = sorted(glob.glob(os.path.join(MODEL_DIR, "*.ts")))
    return [(os.path.dirname(f), os.path.basename(f)) for f in files]

class TestAllModels(unittest.TestCase):
    def test_load_all_models(self):
        failures = []
        for directory, filename in model_test_cases():
            path = os.path.join(directory, filename)
            with self.subTest(model=filename):
                try:
                    model, device = load_model(path, use_gpu=False)
                    self.assertIsNotNone(model)
                    model.eval()
                except Exception as e:
                    failures.append(f"{filename}: {e}")
        if failures:
            self.fail(f"\n{len(failures)} model(s) failed:\n" + "\n".join(failures))
```

**Begründung:** `subTest` gibt einem einzelnen fehlschlagenden Modell nicht den
gesamten Test-Lauf ab, sondern listet alle Fehler am Ende auf.

### 4.3 GPU-Tests

Für GPU-Tests MUSS `torch.cuda.is_available()` vor dem Laden geprüft werden.
Da `load_model(..., use_gpu=True)` aber intern `is_available()` prüft, reicht
ein `@unittest.skipUnless(torch.cuda.is_available(), "CUDA not available")`.

### 4.4 Audio-Qualitätsmetriken

Für Kategorie E werden folgende Metriken verwendet:

```python
import numpy as np

def signal_to_noise_ratio(original, reconstructed):
    """SNR in dB. Höher = besser."""
    noise = original - reconstructed
    ratio = np.var(original) / (np.var(noise) + 1e-10)
    return 10 * np.log10(ratio)

def pearson_correlation(a, b):
    """Pearson-R zwischen zwei 1D-Signalen."""
    return np.corrcoef(a.flatten(), b.flatten())[0, 1]
```

### 4.5 Benchmark-Framework

```python
import time

def benchmark_infer(model, device, method, params, input_block, warmup=5, runs=50):
    """Misst durchschnittliche Inferenzzeit in ms pro Block."""
    # Warmup
    for _ in range(warmup):
        infer_method(model, device, method, params, input_block)
    if device.type == 'cuda':
        torch.cuda.synchronize()
    
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        infer_method(model, device, method, params, input_block)
        if device.type == 'cuda':
            torch.cuda.synchronize()
        times.append(time.perf_counter() - t0)
    
    return {
        'mean_ms': np.mean(times) * 1000,
        'std_ms': np.std(times) * 1000,
        'min_ms': np.min(times) * 1000,
        'max_ms': np.max(times) * 1000,
    }
```

---

## 5. CMake-Integration

Die Python-Tests werden via `ctest` ausgeführt. Dafür:

1. In `CMakeLists.txt` eine `add_test()`-Sektion für die neuen Testdateien:
```cmake
add_test(NAME test_model_loading
  COMMAND "${CMAKE_COMMAND}" -E env PYTHONPATH="${CMAKE_SOURCE_DIR}"
  "${VENV_PYTHON}" "${CMAKE_SOURCE_DIR}/test/test_model_loading.py"
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}")
```

2. Alle bestehenden Python-Tests (`test/test_*.py`) ebenso als CTest-Tests
   registrieren (derzeit nur C++-Tests via `add_test`).

Siehe `test/test_worker_launch.cpp:137-153` für das bestehende Muster des
`--query`-Launches gegen `musicnet.ts`.

---

## 6. Offene Fragen / Entscheidungen

1. **GPU-Tests in CI?** – Die CI-Pipeline (GitHub Actions o.ä.) hat vermutlich
   keine CUDA-GPU. GPU-Tests sind daher `skipIf` und werden nur lokal
   ausgeführt.

2. **Speicherplatz für große Modelle:** `vintage.ts` (460 MB) + `musicnet.ts`
   (237 MB) + weitere → >2 GB Speicher nötig. Tests sollten nacheinander
   geladen werden (nicht parallel) → `gc.collect()` zwischen Tests.

3. **`darbouka_onnx.ts` (ONNX, ausgeschlossen):** Kann NICHT mit
   `torch.jit.load()` geladen werden. `inference_worker.py:load_model()`
   unterstützt derzeit ausschließlich `.ts` (TorchScript). ONNX-Support
   ist ein separates Feature (Phase X, nicht im Scope).
   → **Entscheidung: `darbouka_onnx.ts` wird in allen neuen Tests explizit
   ausgeschlossen** (per `_ONNX_SKIP`-Set oder `.endswith('_onnx.ts')`-Filter).
   Benchmark-Report (T7) enthält Vermerk `ONNX – nicht unterstützt`.

4. **Unbekannte Modelle:** Einige Modelle (`features.ts`, `demo_buffers.ts`,
   etc.) haben keine RAVE-Methoden (`_params`). Tests müssen `get_method_params`
   == {} gracefully behandeln.

---

## 7. Geschätzter Zeitaufwand (Dev-Agent-Tasks)

| Task | Datei | Aufwand | Priorität |
|------|-------|---------|-----------|
| T1. Modell-Lade-Tests | `test/test_model_loading.py` | 3-4 h | 🔴 high |
| T2. mab.info-Integrationstests | `test/test_mab_info_models.py` | 2-3 h | 🔴 high |
| T3. Methoden-Dispatch-Integration | `test/test_infer_all_models.py` | 2-3 h | 🔴 high |
| T4. Audio-Qualitätstests | `test/test_audio_quality.py` | 3-4 h | 🟡 medium |
| T5. Edge-Case-Tests | `test/test_model_edge_cases.py` | 2-3 h | 🟡 medium |
| T6. CMake-Test-Integration | `CMakeLists.txt` | 1 h | 🟡 medium |
| T7. Benchmark-Report-Tool | `test/benchmark_models.py` | 1 h | 🟢 low |

**Summe:** ~14-19 Stunden für vollständige Testabdeckung.

---

## 8. Test-Ausführung

```powershell
# Alle Python-Tests:
.venv\Scripts\python -m pytest test/ -v

# Nur Modell-bezogene Tests:
.venv\Scripts\python -m pytest test/test_model_loading.py test/test_mab_info_models.py test/test_infer_all_models.py -v

# GPU-Tests (lokal, CUDA):
.venv\Scripts\python -m pytest test/test_model_loading.py -v -k "gpu"

# Inklusive Audio-Qualität:
.venv\Scripts\python -m pytest test/test_audio_quality.py -v

# Audio-Qualität + Benchmark (reines Python, CPU + GPU):
.venv\Scripts\python -m pytest test/test_audio_quality.py -v

# Benchmark nur mit GPU:
.venv\Scripts\python -m pytest test/test_audio_quality.py -v -k "gpu or benchmark"

# Benchmark-Report (Standalone-Tool T7, Ergebnisse in doc/benchmark_reports.md):
.venv\Scripts\python test/benchmark_models.py --runs 30 --warmup 5 --report doc/benchmark_reports.md

# Mit CTest (nach CMake-Integration):
cmake --build --preset debug && ctest --preset debug -R "model_loading|mab_info|infer_all|audio"
```

### 8.1 Benchmark-Reports

Die Messergebnisse (CPU/GPU-Latenzen aller Modelle) werden in der separaten
Datei **`doc/benchmark_reports.md`** gesammelt. Jeder Lauf erhält eine
fortlaufende **Testrun-Nummer** und ein **Datum**; neue Messungen werden oben
eingefügt (neuester Lauf zuerst).

Aufruf:
```powershell
# Messen + als neuen Testrun in doc/benchmark_reports.md eintragen:
.venv\Scripts\python test/benchmark_models.py --runs 30 --warmup 5 --report doc/benchmark_reports.md

# Nur messen, nur stdout (kein Eintrag):
.venv\Scripts\python test/benchmark_models.py --runs 30 --warmup 5
```

Befunde aus Testrun 001 (2026-08-11):
- **GPU-Beschleunigung nur bei grossen RAVE-Modellen** (nasa 0.33x, wheel 0.37x,
  voice_vocalset 0.46x) — kleine Modelle sind durch CUDA-Overhead langsamer auf GPU.
- `demo_mc.ts`/`features.ts` haben GPU-inkompatible Operationen (batch-Resize,
  spektrale Routinen) → als "GPU-Fehler" im Report vermerkt.
- `darbouka_onnx.ts` (ONNX) und `afterv2.audio.instr.ts` (RAM > 10 GB) sind
  vom Benchmark ausgeschlossen.

---

## 9. Testumgebung (Computer & Audio-Hardware)

### 9.1 Entwicklungsrechner

| Komponente | Wert |
|------------|------|
| Betriebssystem | Windows 10/11 (64-bit) |
| Max-Version | Max 8+ |
| GPU | NVIDIA (CUDA-fähig, für GPU-Tests) |

### 9.2 Audio-Interface (NUR für Max-Runtime-Tests)

**Wichtig:** Der ASIO-Treiber wird **ausschließlich** für Max-Runtime-Tests
benötigt (Verifikation V1–V6, Phase 5.8, Phase 6.4). Alle Python-Tests in
Kategorie A–F laufen ohne Audio-Interface — sie verarbeiten .wav-Dateien 
blockweise und messen Inferenzzeit direkt in Python.

Für alle Audio-Tests, die Max Runtime benötigen (Verifikation V1–V6,
Phase 5.8 mc.mab~, Phase 6.4 mcs.mab~).

Kategorie-E-Tests (test_audio_quality.py) laufen komplett ohne Audio-Interface
in Python (siehe Einleitung oben).

Folgender ASIO-Treiber ist zu verwenden:

- **Audio-Interface:** Native Instruments Audio Kontrol 1
- **ASIO-Treiber:** Native Instruments Audio Kontrol 1 ASIO Driver

#### Max Audio-Einstellungen (empfohlen)

| Einstellung | Wert | Begründung |
|-------------|------|------------|
| Driver | ASIO | Niedrigste Latenz, kein Windows-Audio-Stack |
| Audio Device | Audio Kontrol 1 | Native Instruments ASIO-Treiber |
| I/O Vector Size | 512 | Standard für 48 kHz RAVE-Modelle |
| Signal Vector Size | 512 | Passend zu block_size=2048 (4 DSP-Ticks) |
| Sample Rate | 48000 Hz | RAVE-Modelle trainieren meist auf 48 kHz |

#### Begründung

- Der **Audio Kontrol 1 ASIO-Treiber** bietet stabile Low-Latency-Performance
  ohne die XRun-Probleme, die mit generischen Windows-Audio-Treibern
  (MME/DirectSound/WASAPI) auftreten können.
- In Kombination mit **Phase 4.5** (ASIO XRun Prevention:
  BELOW_NORMAL_PRIORITY_CLASS + Core-Affinity ohne Core 0) ergibt sich
  eine stabile Testumgebung für Dropout-freie Audio-Verarbeitung.
- Konsistente Treiber-Wahl ist essenziell für reproduzierbare
  Audio-Performance-Messungen (vgl. §6.4 Worst-Case-Szenarien).

