# mab~ Benchmark-Reports

_Gesammelte Performance-Messungen aus `test/benchmark_models.py`. Neueste
Messung steht oben. Jeder Lauf bekommt eine fortlaufende **Testrun-Nummer**
und ein **Datum**. Die Markdown-Tabelle wird automatisch von
`test/benchmark_models.py` angehängt (Flag `--report doc/benchmark_reports.md`)._

---

## Testrun 003 – 2026-08-11 (Verifizierung auto-append)

_Gerät: NVIDIA GeForce RTX 3060 Laptop GPU | Runs=3 Warmup=1 | Methode: `forward` | Messung: CPU+GPU_

| Modell | Größe | Methoden | Block | CPU ms | GPU ms | GPU/CPU |
|--------|-------|----------|-------|--------|--------|---------|
| `demo_attributes.ts` | 0.0 MB | 1 | 512 | **0.853** | **0.779** | 0.91x |
| `demo_buffers.ts` | 0.0 MB | 3 | 512 | **0.448** | **0.810** | 1.81x |
| `demo_mc.ts` | 0.0 MB | 3 | 2048 | **3.449** | GPU-Fehler | – |
| `effects.ts` | 0.0 MB | 8 | 1024 | **0.437** | **0.762** | 1.74x |
| `features.ts` | 0.2 MB | 4 | 1024 | **2.712** | GPU-Fehler | – |
| `modell_30min_27915e19b0.ts` | 1.7 MB | 3 | 512 | **31.770** | **413.835** | 13.03x |
| `musicnet.ts` | 226.0 MB | 4 | 2048 | **176.195** | **314.520** | 1.79x |
| `nasa.ts` | 151.9 MB | 4 | 2048 | **114.413** | **192.700** | 1.68x |
| `thirdModelTest3000Epoche.ts` | 46.6 MB | 3 | 512 | **42.551** | **420.887** | 9.89x |
| `vintage.ts` | 459.5 MB | 4 | 2048 | **201.999** | **371.115** | 1.84x |
| `voice-multi-b2048-r48000-z11.ts` | 143.2 MB | 3 | 2048 | **308.127** | **806.607** | 2.62x |
| `voice_hifitts_b2048_r48000_z16.ts` | 156.3 MB | 3 | 2048 | **252.333** | **390.216** | 1.55x |
| `voice_jvs_b2048_r44100_z16.ts` | 142.4 MB | 3 | 2048 | **292.989** | **641.076** | 2.19x |
| `voice_vctk_b2048_r44100_z22.ts` | 142.4 MB | 3 | 2048 | **308.881** | **651.822** | 2.11x |
| `voice_vocalset_b2048_r48000_z16.ts` | 156.3 MB | 3 | 2048 | **276.155** | **361.155** | 1.31x |
| `water_pondbrain_b2048_r48000_z16.ts` | 115.8 MB | 3 | 2048 | **300.065** | **473.943** | 1.58x |
| `wavetable.ts` | 0.0 MB | 1 | 512 | **0.923** | **34.413** | 37.29x |
| `wheel.ts` | 152.1 MB | 4 | 2048 | **127.402** | **208.751** | 1.64x |

**Anmerkungen:** demo_mc.ts: GPU-Fehler (The following operation failed in the To) features.ts: GPU-Fehler (The following operation failed in the To)

---

## Testrun 002 – 2026-08-11 (niedrige Runs, Warmup klein)

_Gerät: NVIDIA GeForce RTX 3060 Laptop GPU (6 GB) | CPU: 16-Thread (begrenzt
auf 4 Threads via `torch.set_num_threads(4)`) | Runs=3 Warmup=1 |
Methode: `forward` (bzw. erste Methode)._

| Modell | Größe | Methoden | Block | CPU ms | GPU ms | GPU/CPU |
|--------|-------|----------|-------|--------|--------|---------|
| `demo_attributes.ts` | 0.0 MB | 1 | 512 | 0.729 | 1.185 | 1.63x |
| `demo_buffers.ts` | 0.0 MB | 3 | 512 | 0.646 | 1.080 | 1.67x |
| `demo_mc.ts` | 0.0 MB | 3 | 2048 | 3.564 | GPU-Fehler | – |
| `effects.ts` | 0.0 MB | 8 | 1024 | 0.477 | 0.893 | 1.87x |
| `features.ts` | 0.2 MB | 4 | 1024 | 3.971 | GPU-Fehler | – |
| `modell_30min_27915e19b0.ts` | 1.7 MB | 3 | 512 | 41.643 | 466.029 | 11.19x |
| `musicnet.ts` | 226.0 MB | 4 | 2048 | 210.780 | 359.174 | 1.70x |
| `nasa.ts` | 151.9 MB | 4 | 2048 | 140.237 | 230.046 | 1.64x |
| `thirdModelTest3000Epoche.ts` | 46.6 MB | 3 | 512 | 53.168 | 457.785 | 8.61x |
| `vintage.ts` | 459.5 MB | 4 | 2048 | 253.777 | 420.526 | 1.66x |
| `voice-multi-b2048-r48000-z11.ts` | 143.2 MB | 3 | 2048 | 383.314 | 878.985 | 2.29x |
| `voice_hifitts_b2048_r48000_z16.ts` | 156.3 MB | 3 | 2048 | 291.746 | 396.517 | 1.36x |
| `voice_jvs_b2048_r44100_z16.ts` | 142.4 MB | 3 | 2048 | 349.233 | 727.662 | 2.08x |
| `voice_vctk_b2048_r44100_z22.ts` | 142.4 MB | 3 | 2048 | 355.056 | 739.343 | 2.08x |
| `voice_vocalset_b2048_r48000_z16.ts` | 156.3 MB | 3 | 2048 | 313.490 | 394.499 | 1.26x |
| `water_pondbrain_b2048_r48000_z16.ts` | 115.8 MB | 3 | 2048 | 342.278 | 502.642 | 1.47x |
| `wavetable.ts` | 0.0 MB | 1 | 512 | 1.057 | 37.902 | 35.85x |
| `wheel.ts` | 152.1 MB | 4 | 2048 | 165.329 | 242.038 | 1.46x |

**Anmerkungen:** Niedrige Runs → inkl. erster Blocks nach Laden (hohe Werte).
Für stabile Zahlen Runs=30/Warmup=5 verwenden.

---

## Testrun 001 – 2026-08-11 (Basislinie)

_Gerät: NVIDIA GeForce RTX 3060 Laptop GPU (6 GB) | CPU: 16-Thread (begrenzt
auf 4 Threads via `torch.set_num_threads(4)`) | Runs=5 Warmup=2 |
Methode: `forward` (bzw. erste Methode)._

| Modell | Größe | Methoden | Block | CPU ms | GPU ms | GPU/CPU |
|--------|-------|----------|-------|--------|--------|---------|
| `demo_attributes.ts` | 0.0 MB | 1 | 512 | 0.196 | 0.339 | 1.73x |
| `demo_buffers.ts` | 0.0 MB | 3 | 512 | 0.096 | 0.448 | 4.65x |
| `demo_mc.ts` | 0.0 MB | 3 | 2048 | 3.721 | GPU-Fehler | – |
| `effects.ts` | 0.0 MB | 8 | 1024 | 0.164 | 0.434 | 2.65x |
| `features.ts` | 0.2 MB | 4 | 1024 | 0.410 | GPU-Fehler | – |
| `modell_30min_27915e19b0.ts` | 1.7 MB | 3 | 512 | 3.775 | 9.346 | 2.48x |
| `musicnet.ts` | 226.0 MB | 4 | 2048 | 52.599 | 38.106 | 0.72x |
| `nasa.ts` | 151.9 MB | 4 | 2048 | 72.180 | 23.616 | 0.33x |
| `thirdModelTest3000Epoche.ts` | 46.6 MB | 3 | 512 | 18.490 | 21.341 | 1.15x |
| `vintage.ts` | 459.5 MB | 4 | 2048 | 62.225 | 52.342 | 0.84x |
| `voice-multi-b2048-r48000-z11.ts` | 143.2 MB | 3 | 2048 | 45.855 | 60.145 | 1.31x |
| `voice_hifitts_b2048_r48000_z16.ts` | 156.3 MB | 3 | 2048 | 67.976 | 42.635 | 0.63x |
| `voice_jvs_b2048_r44100_z16.ts` | 142.4 MB | 3 | 2048 | 45.012 | 56.052 | 1.25x |
| `voice_vctk_b2048_r44100_z22.ts` | 142.4 MB | 3 | 2048 | 49.637 | 52.913 | 1.07x |
| `voice_vocalset_b2048_r48000_z16.ts` | 156.3 MB | 3 | 2048 | 83.153 | 38.663 | 0.46x |
| `water_pondbrain_b2048_r48000_z16.ts` | 115.8 MB | 3 | 2048 | 40.750 | 33.221 | 0.82x |
| `wavetable.ts` | 0.0 MB | 1 | 512 | 0.269 | 0.600 | 2.23x |
| `wheel.ts` | 152.1 MB | 4 | 2048 | 66.084 | 24.230 | 0.37x |

**Befunde:**
- **GPU-Beschleunigung nur bei grossen RAVE-Modellen** (nasa 0.33x, wheel 0.37x,
  voice_vocalset 0.46x) — kleine Modelle sind durch CUDA-Overhead langsamer auf GPU.
- `demo_mc.ts`/`features.ts` haben GPU-inkompatible Operationen (batch-Resize,
  spektrale Routinen) → als "GPU-Fehler" im Report vermerkt.
- `darbouka_onnx.ts` (ONNX) und `afterv2.audio.instr.ts` (RAM > 10 GB) sind
  vom Benchmark ausgeschlossen.
