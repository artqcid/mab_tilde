#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T5 – Edge-Case- und Stress-Tests (Offline) – Kategorie F.

- TestLoadUnloadCycles: musicnet.ts 10x laden/entladen (kein Leak, kein Crash)
- TestConcurrentModels: 2 Modelle nacheinander aktiv (Threading-/State-Sicherheit)
- TestLargeBlockSize: bufsize=4096 mit musicnet.ts (MAX_BLOCK_SIZE-Grenze)
- TestSmallBlockSize: bufsize=64 mit musicnet.ts (kein Crash)
- TestMaxBlockBoundary: bufsize=0 und bufsize=8192 (Fehlerbehandlung)
- TestMissingMethod: infer_method mit unbekannter Methode (graceful error)
- TestRaveAttributes: demo_attributes.ts set/get (nn_tilde-Parity)
- TestNullInput: Null-Tensor als Input (kein Segfault)

AUSGESCHLOSSEN: `darbouka_onnx.ts` (ONNX), `afterv2.audio.instr.ts` (RAM).
"""

import gc
import glob
import logging
import os
import re
import sys
import unittest

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference_worker import (
    RuntimeAttributes,
    _apply_model_attribute,
    _read_model_attribute,
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

torch.set_num_threads(4)


def _model_path(name):
    return os.path.join(MODEL_DIR, name)


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


def _cleanup():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _make_input(ci, block_size, fill=0.1):
    return np.full((ci, block_size), fill, dtype=np.float32)


MUSICNET = "musicnet.ts"
MUSICNET_PATH = _model_path(MUSICNET)


# ---------------------------------------------------------------------------
# Load/Unload-Cycles
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(MUSICNET_PATH),
                     "musicnet.ts not present")
class TestLoadUnloadCycles(unittest.TestCase):
    """musicnet.ts 10x laden/entladen -> kein Leak, kein Crash."""

    def test_10_load_unload_cycles(self):
        _check_ram("load-unload")
        print("\n--- Load/Unload 10x :: musicnet.ts ---", flush=True)
        for i in range(10):
            print(f"  cycle {i + 1}/10 ...", end=" ", flush=True)
            model, device = load_model(MUSICNET_PATH, use_gpu=False)
            self.assertIsNotNone(model)
            params = get_method_params(model)
            self.assertIn("forward", params)
            bs = compute_layout(params, 512)[0]
            inp = _make_input(1, bs, 0.0)
            infer_method(model, device, "forward", params, inp)
            del model
            _cleanup()
            print("OK", flush=True)
        print("  10 cycles OK", flush=True)


# ---------------------------------------------------------------------------
# Zwei Modelle nacheinander aktiv (State-Isolation)
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(MODEL_DIR),
                     "Model directory not found: D:\\AI-Models\\ts models")
class TestConcurrentModels(unittest.TestCase):
    """Zwei verschiedene Modelle abwechselnd inferieren -> State-Isolation."""

    def test_two_models_interleaved(self):
        _check_ram("concurrent")
        candidates = [m for m in ("musicnet.ts", "nasa.ts")
                      if os.path.exists(_model_path(m))]
        if len(candidates) < 2:
            self.skipTest("need musicnet.ts + nasa.ts")
        print(f"\n--- Concurrent :: {candidates} ---", flush=True)
        models = {}
        try:
            for name in candidates:
                m, d = load_model(_model_path(name), use_gpu=False)
                models[name] = (m, d, get_method_params(m))
                print(f"  loaded {name}", flush=True)
            bs = compute_layout(models[candidates[0]][2], 512)[0]
            for name, (m, d, p) in models.items():
                inp = _make_input(p["forward"][0], bs, 0.01)
                out = infer_method(m, d, "forward", p, inp)
                self.assertTrue(np.all(np.isfinite(out)))
                print(f"  {name} forward OK", flush=True)
        finally:
            del models
            _cleanup()
        print("  concurrent OK", flush=True)


# ---------------------------------------------------------------------------
# Block-Groessen-Grenzen (musicnet.ts)
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(MUSICNET_PATH),
                     "musicnet.ts not present")
class TestLargeBlockSize(unittest.TestCase):
    """bufsize=4096 -> MAX_BLOCK_SIZE-Grenze (4x default 2048)."""

    def test_bufsize_4096(self):
        _check_ram("large-block")
        print("\n--- LargeBlock :: musicnet.ts bufsize=4096 ---", flush=True)
        model, device = load_model(MUSICNET_PATH, use_gpu=False)
        try:
            params = get_method_params(model)
            bs = compute_layout(params, 4096)[0]
            self.assertEqual(bs, 4096)
            inp = _make_input(1, bs, 0.0)
            out = infer_method(model, device, "forward", params, inp)
            self.assertEqual(out.shape, (1, 4096))
            self.assertTrue(np.all(np.isfinite(out)))
            print(f"  forward (1, 4096) OK", flush=True)
        finally:
            del model
            _cleanup()


@unittest.skipUnless(os.path.exists(MUSICNET_PATH),
                     "musicnet.ts not present")
class TestSmallBlockSize(unittest.TestCase):
    """bufsize=64 -> sehr kleine Blocks, kein Crash."""

    def test_bufsize_64(self):
        _check_ram("small-block")
        print("\n--- SmallBlock :: musicnet.ts bufsize=64 ---", flush=True)
        model, device = load_model(MUSICNET_PATH, use_gpu=False)
        try:
            params = get_method_params(model)
            bs = compute_layout(params, 64)[0]
            # block_size darf nie unter die ratio-Anforderung (2048) fallen
            self.assertGreaterEqual(bs, 2048)
            inp = _make_input(1, bs, 0.0)
            out = infer_method(model, device, "forward", params, inp)
            self.assertEqual(out.shape, (1, bs))
            self.assertTrue(np.all(np.isfinite(out)))
            print(f"  forward (1, {bs}) OK", flush=True)
        finally:
            del model
            _cleanup()


@unittest.skipUnless(os.path.exists(MUSICNET_PATH),
                     "musicnet.ts not present")
class TestMaxBlockBoundary(unittest.TestCase):
    """bufsize=0 und bufsize=8192 -> Fehlerbehandlung."""

    def test_bufsize_0(self):
        _check_ram("block-0")
        print("\n--- BlockBoundary :: bufsize=0 ---", flush=True)
        model, device = load_model(MUSICNET_PATH, use_gpu=False)
        try:
            params = get_method_params(model)
            bs = compute_layout(params, 0)[0]
            self.assertGreaterEqual(bs, 1)   # nie 0
            self.assertGreaterEqual(bs, 2048)  # ratio-Anforderung
            inp = _make_input(1, bs, 0.0)
            out = infer_method(model, device, "forward", params, inp)
            self.assertEqual(out.shape, (1, bs))
            print(f"  bufsize=0 -> block_size={bs} OK", flush=True)
        finally:
            del model
            _cleanup()

    def test_bufsize_8192(self):
        _check_ram("block-8192")
        print("\n--- BlockBoundary :: bufsize=8192 ---", flush=True)
        model, device = load_model(MUSICNET_PATH, use_gpu=False)
        try:
            params = get_method_params(model)
            bs = compute_layout(params, 8192)[0]
            self.assertEqual(bs, 8192)
            inp = _make_input(1, bs, 0.0)
            out = infer_method(model, device, "forward", params, inp)
            self.assertEqual(out.shape, (1, 8192))
            self.assertTrue(np.all(np.isfinite(out)))
            print(f"  bufsize=8192 OK", flush=True)
        finally:
            del model
            _cleanup()


# ---------------------------------------------------------------------------
# Unbekannte Methode -> graceful error
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(MUSICNET_PATH),
                     "musicnet.ts not present")
class TestMissingMethod(unittest.TestCase):
    """infer_method mit unbekannter Methode -> AttributeError/KeyError,
    kein Absturz."""

    def test_unknown_method_raises(self):
        _check_ram("missing-method")
        print("\n--- MissingMethod :: musicnet.ts ---", flush=True)
        model, device = load_model(MUSICNET_PATH, use_gpu=False)
        try:
            params = get_method_params(model)
            bs = compute_layout(params, 512)[0]
            inp = _make_input(1, bs, 0.0)
            with self.assertRaises(Exception):
                infer_method(model, device, "definitely_not_a_method",
                             params, inp)
            print(f"  unknown method raised gracefully OK", flush=True)
        finally:
            del model
            _cleanup()


# ---------------------------------------------------------------------------
# RAVE-Attribute set/get (nasa.ts)
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(_model_path("nasa.ts")),
                     "nasa.ts not present")
class TestRaveAttributes(unittest.TestCase):
    """Attribute set/get via RuntimeAttributes/_apply_model_attribute."""

    def test_attribute_set_get(self):
        _check_ram("attributes")
        print("\n--- RaveAttributes :: nasa.ts ---", flush=True)
        model, device = load_model(_model_path("nasa.ts"),
                                   use_gpu=False)
        try:
            ra = RuntimeAttributes()
            # Alle lesbaren Attribute auflisten
            names = [n for n in dir(model)
                     if any(k in n.lower() for k in
                            ("sr", "sample", "latent", "channels", "hop",
                             "window", "n_fft", "gain", "density", "attr"))]
            names = names[:12]  # begrenzt
            read = {}
            for n in names:
                v = _read_model_attribute(model, n)
                if v is not None:
                    read[n] = v
            print(f"  readable attrs: {list(read.keys())}", flush=True)
            # Setzen mit Koatzierung (ggf. schema-konform via RuntimeAttributes)
            for n in list(read.keys())[:3]:
                cur = read[n]
                new = 0.5 if isinstance(cur, (int, float)) else cur
                ra.set(n, new, model=model)
                got = ra.get(n, model=model)
                self.assertIsNotNone(got)
                print(f"  set/get {n}: {got}", flush=True)
            # Inferenz funktioniert weiterhin
            params = get_method_params(model)
            if "forward" in params:
                bs = compute_layout(params, 512)[0]
                out = infer_method(model, device, "forward", params,
                                   _make_input(1, bs, 0.0))
                self.assertTrue(np.all(np.isfinite(out)))
                print(f"  forward nach attr-set OK", flush=True)
        finally:
            del model
            _cleanup()


# ---------------------------------------------------------------------------
# Null-Input (kein Segfault)
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(MUSICNET_PATH),
                     "musicnet.ts not present")
class TestNullInput(unittest.TestCase):
    """Null-Tensor als Input -> kein Segfault, kein Crash."""

    def test_zero_tensor_input(self):
        _check_ram("null-input")
        print("\n--- NullInput :: musicnet.ts ---", flush=True)
        model, device = load_model(MUSICNET_PATH, use_gpu=False)
        try:
            params = get_method_params(model)
            bs = compute_layout(params, 512)[0]
            inp = np.zeros((1, bs), dtype=np.float32)
            out = infer_method(model, device, "forward", params, inp)
            self.assertEqual(out.shape, (1, bs))
            self.assertTrue(np.all(np.isfinite(out)))
            print(f"  zero-tensor forward OK", flush=True)
        finally:
            del model
            _cleanup()


if __name__ == "__main__":
    unittest.main()
