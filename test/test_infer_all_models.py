#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T3 – Methoden-Dispatch-Integrationstests (Offline, ohne Max Runtime) –
Kategorie D.

EIN TEST PRO MODELL – kein kumulativer Speicherdruck. Innerhalb jedes
Tests werden alle Methoden via `subTest()` einzeln getestet, sodass ein
fehlschlagendes Modell/eine fehlschlagende Methode den Rest nicht
blockiert.

Debug-Logging via `logging.DEBUG` auf stderr.
Fortschritts-`print()` auf stdout mit `flush()` nach jedem Schritt.

AUSGESCHLOSSEN: `darbouka_onnx.ts` (ONNX, kein TorchScript).
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
    compute_layout,
    get_method_params,
    infer_method,
    load_model,
)

try:
    import psutil
    def _free_ram_gb():
        return psutil.virtual_memory().available / (1024 ** 3)
except ImportError:
    def _free_ram_gb():
        return 999

RAM_MIN_GB = 2.0

torch.set_num_threads(4)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)

MODEL_DIR = r"D:\AI-Models\ts models"
ONNX_SKIP_SUFFIX = "_onnx.ts"
NON_DETERMINISTIC_METHODS = {"prior"}

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


def _make_input(ci, block_size, rng):
    return rng.uniform(-1.0, 1.0, size=(ci, block_size)).astype(np.float32)


def _check_ram(label):
    free = _free_ram_gb()
    if free < RAM_MIN_GB:
        raise unittest.SkipTest(
            f"RAM too low ({free:.1f} GB free, need {RAM_MIN_GB:.1f} GB) for {label}"
        )
    log.debug("RAM check: %.1f GB free", free)


# ---------------------------------------------------------------------------
# Alle Methoden – ein Test PRO MODELL mit subTest() PRO METHODE
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(MODEL_DIR),
                     "Model directory not found: D:\\AI-Models\\ts models")
class TestInferAllMethods(unittest.TestCase):
    """Ein Test pro Modell, subTest pro Methode."""


def _make_all_methods_test(path):
    def test(self):
        model_name = os.path.basename(path)
        _check_ram(model_name)
        print(f"\n{'='*60}", flush=True)
        print(f"MODEL: {model_name}", flush=True)
        print(f"{'='*60}", flush=True)
        log.info("loading: %s", model_name)
        model, device = load_model(path, use_gpu=False)
        try:
            print(f"  loaded on {device}", flush=True)
            params = get_method_params(model)
            block_size = compute_layout(params, 512)[0]
            methods = list(params.keys())
            print(f"  methods={methods}", flush=True)
            print(f"  block_size={block_size}", flush=True)
            rng = np.random.default_rng(42)
            for method in sorted(methods):
                with self.subTest(method=method):
                    ci, _ri, co, _ro = params[method]
                    print(f"  [{method}] ci={ci} co={co} ...", end=" ", flush=True)
                    inp = _make_input(ci, block_size, rng)
                    out = infer_method(model, device, method, params, inp)
                    self.assertEqual(out.shape, (co, block_size),
                                     f"{method}: shape={out.shape}, expected ({co},{block_size})")
                    self.assertTrue(np.all(np.isfinite(out)),
                                    f"{method}: NaN/Inf in output")
                    print(f"OK (shape={out.shape}, finite={np.all(np.isfinite(out))})", flush=True)
        finally:
            del model
            _cleanup()
            print(f"  cleanup done\n", flush=True)
    return test


for _path in model_files():
    _name = _safe_name(os.path.basename(_path))
    _test_fn = _make_all_methods_test(_path)
    _test_fn.__name__ = f'test_all_methods_{_name}'
    setattr(TestInferAllMethods, _test_fn.__name__, _test_fn)


# ---------------------------------------------------------------------------
# Forward mit Zufalls-Input – ein Test pro forward-faehiges Modell
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(MODEL_DIR),
                     "Model directory not found: D:\\AI-Models\\ts models")
class TestInferRandInput(unittest.TestCase):
    """forward mit Zufalls-Input pro Modell einzeln."""


def _make_forward_rand_test(path):
    def test(self):
        model_name = os.path.basename(path)
        _check_ram(model_name)
        print(f"\n--- RandInput :: {model_name} :: forward ---", flush=True)
        model, device = load_model(path, use_gpu=False)
        try:
            params = get_method_params(model)
            if "forward" not in params:
                print(f"  SKIP: no forward method", flush=True)
                self.skipTest("no forward method")
            ci, _ri, co, _ro = params["forward"]
            block_size = compute_layout(params, 512)[0]
            print(f"  ci={ci} co={co} block_size={block_size}", flush=True)
            rng = np.random.default_rng(7)
            inp = _make_input(ci, block_size, rng)
            out = infer_method(model, device, "forward", params, inp)
            self.assertEqual(out.shape, (co, block_size))
            self.assertTrue(np.all(np.isfinite(out)))
            print(f"  OK", flush=True)
        finally:
            del model
            _cleanup()
    return test


for _path in model_files():
    _name = _safe_name(os.path.basename(_path))
    _test_fn = _make_forward_rand_test(_path)
    _test_fn.__name__ = f'test_forward_rand_{_name}'
    setattr(TestInferRandInput, _test_fn.__name__, _test_fn)


# ---------------------------------------------------------------------------
# Determinismus – ein Test pro Modell
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(MODEL_DIR),
                     "Model directory not found: D:\\AI-Models\\ts models")
class TestInferDeterministic(unittest.TestCase):
    """Gleicher Input → gleicher Output (forward/encode/decode, nicht prior)."""


def _make_deterministic_test(path):
    def test(self):
        model_name = os.path.basename(path)
        _check_ram(model_name)
        model, device = load_model(path, use_gpu=False)
        try:
            params = get_method_params(model)
            candidates = [m for m in ("forward", "encode", "decode")
                          if m in params]
            if not candidates:
                self.skipTest("no deterministic method available")
            stateful = len([m for m in ("encode", "decode") if m in params]) > 0
            if stateful or len(candidates) > 1:
                self.skipTest(f"model is stateful (encode/decode present)")
            print(f"\n--- Deterministic :: {model_name} ---", flush=True)
            block_size = compute_layout(params, 512)[0]
            rng = np.random.default_rng(11)
            for method in candidates:
                with self.subTest(method=method):
                    print(f"  [{method}] ...", end=" ", flush=True)
                    ci, _ri, _co, _ro = params[method]
                    inp = _make_input(ci, block_size, rng)
                    out1 = infer_method(model, device, method, params, inp)
                    out2 = infer_method(model, device, method, params, inp)
                    np.testing.assert_array_equal(out1, out2)
                    print(f"OK", flush=True)
        finally:
            del model
            _cleanup()
    return test


for _path in model_files():
    _name = _safe_name(os.path.basename(_path))
    _test_fn = _make_deterministic_test(_path)
    _test_fn.__name__ = f'test_deterministic_{_name}'
    setattr(TestInferDeterministic, _test_fn.__name__, _test_fn)


if __name__ == "__main__":
    unittest.main()
