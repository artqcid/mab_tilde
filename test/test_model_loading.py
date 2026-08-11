#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T1 – Modell-Lade-Tests (Offline, ohne Max Runtime) – Kategorie B.

Laedt jedes TorchScript-Modell aus D:\\AI-Models\\ts models einzeln auf CPU
(und, falls CUDA verfuegbar ist, auch auf GPU), ruft `get_method_params()`
und `compute_layout()` auf und validiert die Layout-Werte.

JEDES MODELL HAT SEINE EIGENE TEST-METHODE → saubere Trennung, kein
kumulativer Speicherdruck. Dynamisch via setattr() generiert.

AUSGESCHLOSSEN: `darbouka_onnx.ts` (ONNX-Container, kein TorchScript –
torch.jit.load() schlaeft fehl). Siehe doc/test_strategy.md §6.3.
"""

import gc
import glob
import os
import re
import sys
import unittest

import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference_worker import (
    compute_layout,
    get_method_params,
    load_model,
)

MODEL_DIR = r"D:\AI-Models\ts models"

ONNX_SKIP_SUFFIX = "_onnx.ts"


def model_files():
    if not os.path.isdir(MODEL_DIR):
        return []
    files = [f for f in glob.glob(os.path.join(MODEL_DIR, "*.ts"))
             if not os.path.basename(f).lower().endswith(ONNX_SKIP_SUFFIX)]
    return sorted(files)


def _safe_name(filename):
    return re.sub(r'[^a-zA-Z0-9]', '_', filename)


def _cleanup():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


# ---------------------------------------------------------------------------
# CPU-Lade-Tests – ein Test pro Modell
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(MODEL_DIR),
                     "Model directory not found: D:\\AI-Models\\ts models")
class TestModelLoadingCPU(unittest.TestCase):
    """Jedes Modell einzeln auf CPU laden + eval() setzen."""


def _make_cpu_test(path):
    def test(self):
        model, device = load_model(path, use_gpu=False)
        try:
            self.assertIsNotNone(model)
            model.eval()
            self.assertEqual(device.type, "cpu")
        finally:
            del model
            _cleanup()
    return test


for _path in model_files():
    _name = _safe_name(os.path.basename(_path))
    setattr(TestModelLoadingCPU, f'test_cpu_{_name}',
            _make_cpu_test(_path))


# ---------------------------------------------------------------------------
# GPU-Lade-Tests – ein Test pro Modell (nur wenn CUDA verfuegbar)
# ---------------------------------------------------------------------------

@unittest.skipUnless(torch.cuda.is_available(), "CUDA not available")
class TestModelLoadingGPU(unittest.TestCase):
    """Jedes Modell einzeln auf GPU laden + eval() setzen."""


def _make_gpu_test(path):
    def test(self):
        model, device = load_model(path, use_gpu=True)
        try:
            self.assertIsNotNone(model)
            model.eval()
            self.assertEqual(device.type, "cuda")
        finally:
            del model
            _cleanup()
    return test


for _path in model_files():
    _name = _safe_name(os.path.basename(_path))
    setattr(TestModelLoadingGPU, f'test_gpu_{_name}',
            _make_gpu_test(_path))


# ---------------------------------------------------------------------------
# Layout-Validierung – ein Test pro Modell
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(MODEL_DIR),
                     "Model directory not found: D:\\AI-Models\\ts models")
class TestModelLayout(unittest.TestCase):
    """get_method_params + compute_layout – ein Test pro Modell."""


def _make_layout_test(path):
    def test(self):
        model, _device = load_model(path, use_gpu=False)
        try:
            params = get_method_params(model)
            self.assertIsInstance(params, dict)
            for method, p in params.items():
                self.assertEqual(len(p), 4)
                ci, ri, co, ro = p
                self.assertGreaterEqual(ci, 1)
                self.assertGreaterEqual(ri, 1)
                self.assertGreaterEqual(co, 1)
                self.assertGreaterEqual(ro, 1)
            bs, mx_in, mx_out = compute_layout(params, 512)
            self.assertGreaterEqual(bs, 1)
            self.assertGreaterEqual(mx_in, 1)
            self.assertGreaterEqual(mx_out, 1)
            bs0, _mi, _mo = compute_layout(params, 0)
            self.assertGreaterEqual(bs0, 1)
        finally:
            del model
            _cleanup()
    return test


for _path in model_files():
    _name = _safe_name(os.path.basename(_path))
    setattr(TestModelLayout, f'test_layout_{_name}',
            _make_layout_test(_path))


# ---------------------------------------------------------------------------
# Modell-Inventar (bleibt als Einzeltest – laedt keine Modelle)
# ---------------------------------------------------------------------------

class TestModelInventory(unittest.TestCase):
    EXPECTED = [
        "birds_dawnchorus_b2048_r48000_z8.ts",
        "birds_motherbird_b2048_r48000_z16.ts",
        "birds_pluma_b2048_r48000_z12.ts",
        "crozzoli_bigensemblesmusic_18d.ts",
        "freesoundloop10k_raspi_b2048_r44100_z16.ts",
        "humpbacks_pondbrain_b2048_r48000_z20.ts",
        "magnets_b2048_r48000_z8.ts",
        "marinemammals_pondbrain_b2048_r48000_z20.ts",
        "modell_30min_27915e19b0.ts",
        "mrp_strengjavera_b2048_r44100_z16.ts",
        "musicnet.ts",
        "nasa.ts",
        "sol_ordinario_fast.ts",
        "thirdModelTest3000Epoche.ts",
        "vintage.ts",
        "voice-multi-b2048-r48000-z11.ts",
        "voice_hifitts_b2048_r48000_z16.ts",
        "voice_jvs_b2048_r44100_z16.ts",
        "voice_vctk_b2048_r44100_z22.ts",
        "voice_vocalset_b2048_r48000_z16.ts",
        "water_pondbrain_b2048_r48000_z16.ts",
        "wavetable.ts",
        "wheel.ts",
    ]

    @unittest.skipUnless(os.path.exists(MODEL_DIR),
                         "Model directory not found: D:\\AI-Models\\ts models")
    def test_inventory_matches_expected_list(self):
        actual = [os.path.basename(f) for f in model_files()]
        self.assertEqual(actual, self.EXPECTED)

    def test_onnx_container_excluded(self):
        self.assertTrue(os.path.basename(os.path.join(
            MODEL_DIR, "darbouka_onnx.ts")).endswith(ONNX_SKIP_SUFFIX))


if __name__ == "__main__":
    unittest.main()
