# mab~ – Dev Architecture Reference

_Stand: 2026-08-11. Architektur-Wissen & Historie. Keine aktiven Tasks (siehe `doc/checklist.md`)._

## 1. Project Purpose

Crash-safe, process-isolated MaxMSP external family (`mab~`, `mc.mab~`, `mcs.mab~`,
`mab.info`) + Python backend (`inference_worker.py`), replacing `nn_tilde` for
TorchScript models (RAVE, AFTER) on Windows.

Core design: Python worker process + Windows shared memory + lock-free SPSC ring
buffer. No libtorch in Max. Supports CPU/GPU inference, dynamic reload, runtime
attribute setting, method-aware IO (`encode`/`decode`/`forward`).

## 2. Implemented Phases (History)

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Setup / Build-System (Native Max SDK, CMake Presets) | ✅ |
| 1 | Core C++ External (async init, Shared Memory v1, Messages) | ✅ |
| 2 | Python Backend (Handshake, Inferenz-Loop, Attribute) | ✅ |
| 3 | Method-aware IO / Latent Inlets (Header v2, `block_accumulator`, `infer_method`) | ✅ |
| 4 | `mab.info` (process-isolated model inspector) | ✅ |
| 4.5 | ASIO XRun prevention (`BELOW_NORMAL_PRIORITY_CLASS` + core affinity) | ✅ |
| 4.6 | nn_tilde parity P1–P6 (attribute passthrough, gpu setter, void mode, download/delete) | ✅ |
| 5 | `mc.mab~` Multichannel (Header v3 `channel_map`, 1-in-1-out MC-IO, `Z_MC_INLETS`, `chans`) | ✅ (Max-verifiziert) |

**Open phases:** 6 (`mcs.mab~`). See `doc/checklist.md`.

## 3. Architecture Decisions

### 3.1 Process Isolation
Python runs in separate process. No PyTorch in Max address space. Benefits:
- Crash isolation (worker crash → C++ stays alive in bypass mode)
- No GIL contention with Max GUI thread
- No C++ threading issues (nn_tilde Windows memory leak #24237 avoided)

### 3.2 Lock-Free IPC
- Shared memory `MabSharedMem_{instance_id}` with `SharedMemoryHeader` v4
- SPSC ring buffer for control messages (head=C++ producer, tail=Python consumer)
- Named events for signaling (`MabReadyEvent_{instance_id}`, `MabInputReadyEvent_{instance_id}`)
- Double-buffering for audio blocks during inference overlap
- FR5: `instance_id` = Objekt-Zeiger (per-Objekt eindeutig, multiinstanzfähig)

### 3.3 Async Initialization
`mab_tilde_new` never blocks Max main thread. Worker spawns in detached C++
background thread; object starts in bypass mode. IO rebuild via `t_qelem` on
Max main thread after handshake completes.

### 3.4 RT Safety
- No OS locks in `perform64` (`WaitForSingleObject`, mutexes)
- Only atomics (`InterlockedExchange`, `InterlockedIncrement`)
- Worker: `BELOW_NORMAL_PRIORITY_CLASS`, affinity excludes core 0
- `torch.set_num_threads(1)`, `OMP/MKL/OPENBLAS_NUM_THREADS=1` (CPU mode only)
- `gc.disable()` in inference loop

### 3.5 Method-Aware IO (Header v2)
Model exposes `{method}_params = [channels_in, ratio_in, channels_out, ratio_out]`.
C++ dynamically recreates inlets/outlets after handshake. Latent buffers use
`block_accumulator` for rate conversion (e.g., RAVE decode: ratio 2048).

## 4. Comparison with nn_tilde

| Aspect | nn_tilde | mab_tilde |
|--------|----------|-----------|
| Python integration | Embedded via pybind11/libtorch | Separate process + SHM IPC |
| Windows issues | Memory leak (#24237), threading disabled | Process-isolated, no C++-Python threading |
| Crash handling | Silence output (`fill_with_zero()`) | Bypass mode + `reload` command |
| Async init | Thread-based (`m_use_thread=false` on Win) | Background thread + atomic ready flag |
| Lock-free audio | Ring buffer + atomics | Same, plus double-buffering |
| Model inspection | `nn.info` loads PyTorch in Max process | `mab.info` = `--query` worker subprocess |

## 5. Success Criteria

- **Functional**: All Max messages (`enable`, `gpu`, `reload`, `dump`, `set`, `get`, `method`, `load`, `print_available_models`, `download`, `delete`) work as specified.
- **Performance**: No audible dropouts; latency <= 5 ms; CPU usage < 15% single core.
- **Stability**: Clean shutdown; no zombie processes; no memory leaks.
- **Compatibility**: Windows 10/11, Max 8+.
- **RT Safety**: No blocking calls in audio thread; lock-free synchronization.
- **Documentation**: Help patches + maxref.xml for `mab~` and `mab.info`.

## 6. Audio Performance Analysis (Phase 3 / Header v2)

### 6.1 Latency Budget

`L_total = L_accumulation + L_inference + L_drain + L_polling`

| Mode | ratio_in | block_size | Accum | Poll | Inference (CPU) | Inference (GPU) | Drain | **Total CPU** | **Total GPU** |
|------|----------|------------|-------|------|-----------------|-----------------|-------|---------------|---------------|
| forward (ratio=1) | 1 | 512 | 10.7 ms | 0.5 ms | 2–8 ms | 0.5–2 ms | 10.7 ms | **24–30 ms** | **22–24 ms** |
| decode (RAVE) | 2048 | 2048 | 42.7 ms | 0.5 ms | 5–15 ms | 1–3 ms | 42.7 ms | **91–101 ms** | **87–89 ms** |
| encode (RAVE) | 1 | 2048 | 42.7 ms | 0.5 ms | 5–15 ms | 1–3 ms | 42.7 ms | **91–101 ms** | **87–89 ms** |

*(48 kHz, Max vector_size=512, typical RAVE model times)*

### 6.2 DSP Tick Operations (perform64)

| # | Operation | RT-safe? | Note |
|---|-----------|----------|------|
| 1 | `block_accumulate_write` (double->float) | ✅ | ~4–8 us for 16chx512 |
| 2 | `method_id` compare (32-bit atomic) | ✅ | No torn-read |
| 3 | `InterlockedExchange` (flags) | ✅ | Atomic XCHG |
| 4 | `block_accumulate_read` (float->double) | ✅ | SIMD via SSE2 intrinsics |
| 5 | Crash-monitor (via `t_clock`, not perform64) | ✅ | 100ms interval |

### 6.3 Buffering Model
Double-buffering: two input + two output buffers. During Python inference,
C++ accumulates in alternate buffer. Swaps on completion. Eliminates sample
loss during inference (was a problem with single-buffer ping-pong).

### 6.4 Worst-Case Scenarios

| Scenario | Impact | Mitigation |
|----------|--------|------------|
| Inference > block period | Periodic silence gaps | Double-buffering |
| Python GC Gen-2 pause (~50ms) | 1 block silence | `gc.disable()` + manual collect every 100 blocks |
| Worker crash | Bypass mode + console error | Crash monitor via `t_clock` |
| ASIO buffer overflow | Dropouts (worker starves audio) | Phase 4.5: BELOW_NORMAL + core 0 excluded |

## 7. Architecture Improvement History

All completed. Documented here for reference.

### Completed (A1–A11)

- **A1 – Double-Buffering**: Eliminated sample loss during inference via alternate buffer swap. `mab_tilde.cpp`, `inference_worker.py`, Header v2.
- **A2 – Crash Monitor from t_clock**: `GetExitCodeProcess` removed from perform64. `mab_tilde_check_crash` via `clock_fdelay(100ms)`.
- **A3 – Stale Test Removed**: `test_shared_memory_management.cpp` deleted (covered by `test_shared_memory_header_compatibility`).
- **A4 – Event-Based Polling**: Worker uses `WaitForSingleObject` on named event instead of `time.sleep(0.001)`. `MabInputReadyEvent_{instance_id}`.
- **A5 – Python GC Disabled**: `gc.disable()` before main loop; manual `gc.collect()` every 100 blocks.
- **A6 – SIMD float<->double**: SSE2 intrinsics in `convert_d2f`/`convert_f2d` (`block_accumulator.h`).
- **A7 – Torn-Read Fix**: `method_id` (uint32_t hash) replaces `strcmp(method)` in perform64.
- **A8 – Orphan Tests Cleanup**: `test_shared_memory_management.cpp`, `test_ext_main.cpp` deleted.
- **A9 – Parity Doc Updated**: `nn_tilde_parity.md` reflects P1-P6 implemented.
- **A10 – Sections 8-10 Consolidated**: Replaced narrative with compact reference table.
- **A11 – Help Files Created**: `help/mab~.maxhelp`, `help/mab.info.maxhelp`, `docs/mab~.maxref.xml`, `docs/mab.info.maxref.xml`.

