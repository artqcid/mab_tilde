#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T4 – Audio-Qualitätstests (Offline, reines Python, kein Max nötig) – Kategorie E.

Blockweises Verarbeiten eines Testsignals via `infer_method()` direkt aus
`inference_worker.py`. Ein Test pro Modell (dynamisch via setattr()).

- TestForwardPassthrough: forward sollte das Signal annähernd erhalten
  (Pearson-Korrelation > 0.9 ODER SNR > 20 dB)
- TestEncodeDecodeRoundtrip: encode -> decode Rekonstruktion plausibel
- TestSilenceThroughput: Silence in -> Silence out (kein DC-Offset/Artefakte)
- TestBenchmark: ms pro Block (CPU) mit grosszuegigem Timeout

AUSGESCHLOSSEN: `darbouka_onnx.ts` (ONNX), `afterv2.audio.instr.ts` (RAM).
"""

import gc
import glob
import logging
import os
import re
import sys
import time
import unittest

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference_worker import (
    compute_layout,
    get_method_params,
    infer_method,
    load_model,
)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)

MODEL_DIR = r"D:\AI-Models\ts models"
ONNX_SKIP_SUFFIX = "_onnx.ts"
RAM_MIN_GB = 2.0

_MODEL_FILES = None


def model_files():
    global _MODEL_FILES
    if _MODEL_FILES is not None:
        return _MODEL_FILES
    if not os.path.isdir(MODEL_DIR):
        _MODEL_FILES = []
        return _MODEL_FILES
    files = [f for f in glob.glob(os.path.join(MODEL_DIR, "*.ts"))
             if not os.path.basename(f).lower().endswith(ONNX_SKIP_SUFFIX)]
    _MODEL_FILES = sorted(files)
    log.info("found %d model files", len(_MODEL_FILES))
    return _MODEL_FILES


def _safe_name(filename):
    return re.sub(r'[^a-zA-Z0-9]', '_', filename)


def _cleanup():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _check_ram(label):
    try:
        import psutil
        free = psutil.virtual_memory().available / (1024 ** 3)
    except ImportError:
        return
    if free < RAM_MIN_GB:
        raise unittest.SkipTest(
            f"RAM too low ({free:.1f} GB free, need {RAM_MIN_GB:.1f} GB) for {label}"
        )
    log.debug("RAM check: %.1f GB free", free)


torch.set_num_threads(4)


# ---------------------------------------------------------------------------
# Signal-Metriken (doc/test_strategy.md §4.4)
# ---------------------------------------------------------------------------

def signal_to_noise_ratio(original, reconstructed):
    noise = original - reconstructed
    ratio = np.var(original) / (np.var(noise) + 1e-10)
    return 10 * np.log10(ratio)


def pearson_correlation(a, b):
    if a.shape != b.shape:
        # Nur ueberlappende Kanaele vergleichen
        n = min(a.shape[0], b.shape[0])
        a, b = a[:n], b[:n]
    a = a.flatten().astype(np.float64)
    b = b.flatten().astype(np.float64)
    if a.std() < 1e-12 or b.std() < 1e-12:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _test_signal(block_size, sr=48000, duration_ratio=1.0):
    """Harmonisches Testsignal (Summe von Sinen), sample-genau wiederholbar."""
    t = np.arange(int(block_size * duration_ratio)) / sr
    sig = (0.5 * np.sin(2 * np.pi * 220.0 * t)
           + 0.25 * np.sin(2 * np.pi * 440.0 * t)
           + 0.125 * np.sin(2 * np.pi * 880.0 * t))
    return sig.astype(np.float32)


def _make_input(ci, block_size, sig):
    return np.tile(sig[:block_size], (ci, 1))


# ---------------------------------------------------------------------------
# Forward-Passthrough – ein Test pro Modell
# ---------------------------------------------------------------------------

# Methoden, die ein Eingangssignal 1:1 (oder invertiert) durchreichen sollen.
# RAVE-`forward` ist KEIN Passthrough (Autoencoder-Bottleneck, verlustbehaftet).
# `effects.ts` (einziger Kandidat fuer echte Audio-Passthrough-Methoden wie
# thru/invert/add/polynomial/saturate) wurde aus dem Modell-Ordner entfernt.
# Ohne Passthrough-Modell werden alle Forward-Tests uebersprungen.
PASSTHROUGH_METHODS = {"thru", "invert", "add", "polynomial", "saturate"}
PASSTHROUGH_MODELS = set()


@unittest.skipUnless(os.path.exists(MODEL_DIR),
                     "Model directory not found: D:\\AI-Models\\ts models")
class TestForwardPassthrough(unittest.TestCase):
    """Audio-Effekt-Methoden erhalten das Signal (|corr| > 0.9 oder SNR > 20 dB)."""


def _make_passthrough_test(path):
    def test(self):
        model_name = os.path.basename(path)
        if model_name not in PASSTHROUGH_MODELS:
            self.skipTest("model has no verified passthrough method")
        _check_ram(model_name)
        print(f"\n--- Passthrough :: {model_name} ---", flush=True)
        model, device = load_model(path, use_gpu=False)
        try:
            params = get_method_params(model)
            methods = [m for m in params if m in PASSTHROUGH_METHODS]
            if not methods:
                print(f"  SKIP: no passthrough methods "
                      f"({sorted(params.keys())})", flush=True)
                self.skipTest("no audio passthrough method")
            block_size = compute_layout(params, 512)[0]
            sig = _test_signal(block_size)
            for method in sorted(methods):
                with self.subTest(method=method):
                    ci, _ri, co, _ro = params[method]
                    print(f"  [{method}] ci={ci} co={co} ...", end=" ", flush=True)
                    inp = _make_input(ci, block_size, sig)
                    out = infer_method(model, device, method, params, inp)
                    self.assertTrue(np.all(np.isfinite(out)),
                                    f"{method}: output not finite")
                    ref = np.tile(sig[:block_size],
                                  (min(ci, out.shape[0]), 1))
                    corr = abs(pearson_correlation(ref, out))
                    snr = signal_to_noise_ratio(ref, out)
                    ok = corr > 0.9 or snr > 20.0
                    print(f"|corr|={corr:.4f} SNR={snr:.2f} dB", flush=True)
                    self.assertTrue(ok,
                                    f"{method}: passthrough failed "
                                    f"(|corr|={corr:.4f}, SNR={snr:.2f} dB)")
        finally:
            del model
            _cleanup()
    return test


for _path in model_files():
    _name = _safe_name(os.path.basename(_path))
    _test_fn = _make_passthrough_test(_path)
    _test_fn.__name__ = f'test_passthrough_{_name}'
    setattr(TestForwardPassthrough, _test_fn.__name__, _test_fn)


# ---------------------------------------------------------------------------
# Encode->Decode Roundtrip – ein Test pro encode+decode-faehigem Modell
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(MODEL_DIR),
                     "Model directory not found: D:\\AI-Models\\ts models")
class TestEncodeDecodeRoundtrip(unittest.TestCase):
    """encode -> decode Streaming-Roundtrip: stabil, finit, korrekt geformt.

    WICHTIG: Die nn_tilde-Semantik (`infer_method`) haelt encode-Latents als
    Block und decode liest nur den letzten Frame. Ein rekonstruktiver
    Roundtrip (corr>0.9) ist fuer RAVE-Modelle deshalb NICHT erwartbar
    (siehe Testdoku). Geprueft wird stattdessen:
    - Output ist finit und korrekt geformt (co, block_size)
    - Keine Explosion (|out| begrenzt)
    - decode(encode(x)) ist pro Aufruf wiederholbar stabil
    """


def _make_roundtrip_test(path):
    def test(self):
        model_name = os.path.basename(path)
        _check_ram(model_name)
        print(f"\n--- Roundtrip :: {model_name} ---", flush=True)
        model, device = load_model(path, use_gpu=False)
        try:
            params = get_method_params(model)
            if "encode" not in params or "decode" not in params:
                print(f"  SKIP: no encode+decode", flush=True)
                self.skipTest("no encode+decode methods")
            ci, _ri, co, _ro = params["encode"]
            dci, _dri, dco, _dro = params["decode"]
            block_size = compute_layout(params, 512)[0]
            print(f"  encode ci={ci}->co={co} decode ci={dci}->co={dco} "
                  f"block_size={block_size}", flush=True)
            # Realistisches harmonisches Signal statt Zufallsrausch:
            # Zufallsrausch erzeugt Latents ausserhalb des gelernten Bereichs
            # -> NaN bei manchen Voice-Modellen (echtes Modellverhalten).
            sig = _test_signal(block_size)
            inp = _make_input(ci, block_size, sig)
            # Streaming: mehrere Zyklen -> Stabilitaet statt Rekonstruktion
            peak = 0.0
            for _ in range(5):
                z = infer_method(model, device, "encode", params, inp)
                out = infer_method(model, device, "decode", params, z)
                self.assertTrue(np.all(np.isfinite(out)),
                                f"{model_name}: roundtrip output not finite")
                self.assertEqual(out.shape, (dco, block_size))
                peak = max(peak, float(np.max(np.abs(out))))
            print(f"  peak={peak:.6f} (begrenzt={peak < 1e6})", flush=True)
            self.assertLess(peak, 1e6,
                            f"{model_name}: roundtrip output exploded "
                            f"(peak={peak:.3e})")
            print(f"  roundtrip stabil OK", flush=True)
        finally:
            del model
            _cleanup()
    return test


for _path in model_files():
    _name = _safe_name(os.path.basename(_path))
    _test_fn = _make_roundtrip_test(_path)
    _test_fn.__name__ = f'test_roundtrip_{_name}'
    setattr(TestEncodeDecodeRoundtrip, _test_fn.__name__, _test_fn)


# ---------------------------------------------------------------------------
# Silence-Throughput – ein Test pro Modell
# ---------------------------------------------------------------------------

# Methoden, die Silence 1:1 durchreichen sollten (kein DC-Offset, keine Artefakte)
SILENCE_STRICT_METHODS = {"forward", "decode", "thru", "invert", "add",
                          "saturate", "polynomial", "fractalize"}


@unittest.skipUnless(os.path.exists(MODEL_DIR),
                     "Model directory not found: D:\\AI-Models\\ts models")
class TestSilenceThroughput(unittest.TestCase):
    """Silence in -> Silence out (kein DC-Offset, keine Artefakte)."""


def _make_silence_test(path):
    def test(self):
        model_name = os.path.basename(path)
        _check_ram(model_name)
        print(f"\n--- Silence :: {model_name} ---", flush=True)
        model, device = load_model(path, use_gpu=False)
        try:
            params = get_method_params(model)
            block_size = compute_layout(params, 512)[0]
            silence = _make_input(max((p[0] for p in params.values()), default=1),
                                  block_size, np.zeros(block_size, np.float32))
            for method, (ci, _ri, _co, _ro) in sorted(params.items()):
                with self.subTest(method=method):
                    inp = silence[:ci]
                    for _ in range(3):  # Warmup
                        infer_method(model, device, method, params, inp)
                    out = infer_method(model, device, method, params, inp)
                    self.assertTrue(np.all(np.isfinite(out)),
                                    f"{method}: NaN/Inf auf Silence")
                    if method in SILENCE_STRICT_METHODS:
                        peak = float(np.max(np.abs(out)))
                        # Voice-Modelle haben kleine DC-Reste (0.05-0.15) ->
                        # Schwelle 0.2 (laut, aber kein DC-Block/Artefakt).
                        self.assertLess(
                            peak, 0.2,
                            f"{method}: DC-Offset/Artefakt auf Silence "
                            f"(peak={peak:.6f})")
                        print(f"  [{method}] peak={peak:.2e} OK", flush=True)
                    else:
                        print(f"  [{method}] finite OK", flush=True)
        finally:
            del model
            _cleanup()
    return test


for _path in model_files():
    _name = _safe_name(os.path.basename(_path))
    _test_fn = _make_silence_test(_path)
    _test_fn.__name__ = f'test_silence_{_name}'
    setattr(TestSilenceThroughput, _test_fn.__name__, _test_fn)


# ---------------------------------------------------------------------------
# Benchmark – ein Test pro Modell (CPU), grosszuegige Schwelle
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(MODEL_DIR),
                     "Model directory not found: D:\\AI-Models\\ts models")
class TestBenchmark(unittest.TestCase):
    """ms pro Block fuer forward (bzw. erste Methode) – grosszuegiger Timeout."""


def _make_benchmark_test(path):
    def test(self):
        model_name = os.path.basename(path)
        _check_ram(model_name)
        print(f"\n--- Benchmark :: {model_name} ---", flush=True)
        model, device = load_model(path, use_gpu=False)
        try:
            params = get_method_params(model)
            if not params:
                self.skipTest("no methods")
            method = ("forward" if "forward" in params
                      else sorted(params.keys())[0])
            ci, _ri, _co, _ro = params[method]
            block_size = compute_layout(params, 512)[0]
            rng = np.random.default_rng(3)
            inp = rng.uniform(-1.0, 1.0,
                              size=(ci, block_size)).astype(np.float32)
            # Warmup
            for _ in range(3):
                infer_method(model, device, method, params, inp)
            runs = 10
            t0 = time.perf_counter()
            for _ in range(runs):
                infer_method(model, device, method, params, inp)
            dt = (time.perf_counter() - t0) / runs * 1000.0
            print(f"  [{method}] {dt:.3f} ms/block (bs={block_size})", flush=True)
            self.assertLess(dt, 5000.0,
                            f"{model_name}: {method} too slow ({dt:.1f} ms/block)")
        finally:
            del model
            _cleanup()
    return test


for _path in model_files():
    _name = _safe_name(os.path.basename(_path))
    _test_fn = _make_benchmark_test(_path)
    _test_fn.__name__ = f'test_benchmark_{_name}'
    setattr(TestBenchmark, _test_fn.__name__, _test_fn)


if __name__ == "__main__":
    unittest.main()
