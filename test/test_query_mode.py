#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unit tests for the Phase 4 --query mode (mab.info backend).

Covers:
- detect_model_type / get_method_labels / detect_model_attributes
- collect_model_info: metadata dict for a fake RAVE-like model
- print_info_block: the MABJSON + MAB_INFO_BEGIN/END format C++ parses
"""

import io
import os
import sys
import unittest
from contextlib import redirect_stdout

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference_worker import (
    collect_model_info,
    detect_model_attributes,
    detect_model_type,
    get_method_attributes,
    get_method_labels,
    print_info_block,
    resolve_model_path,
)

MUSICNET_PARAMS = {
    'decode': (16, 2048, 1, 1),
    'encode': (1, 1, 16, 2048),
    'forward': (1, 1, 1, 1),
    'prior': (1, 2048, 16, 2048),
}


class FakeRaveModel:
    """Mimics the surface of a scripted RAVE model (VariationalScriptedRAVE)."""

    def __init__(self):
        for name, (ci, ri, co, ro) in MUSICNET_PARAMS.items():
            setattr(self, name + "_params", torch.tensor(
                [ci, ri, co, ro], dtype=torch.long))
        setattr(self, "decode_input_labels", ["(signal) Latent dimension %d" % i
                                              for i in range(1, 17)])
        setattr(self, "decode_output_labels", ["(signal) Channel 1"])
        self.latent_mean = torch.zeros(128)      # 128 elements -> skipped
        self.sample_rate = 44100.0

    @property
    def _c(self):
        class TypeName:
            def name(self):
                return "VariationalScriptedRAVE"
        class C:
            def get_methods(self):
                return list(MUSICNET_PARAMS.keys())
            def _type(self):
                return TypeName()
        return C()


class TestResolveModelPath(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "models"), exist_ok=True)
        with open(os.path.join(self.tmp, "models", "mymodel.ts"), "w") as f:
            f.write("fake")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_existing_absolute_path_unchanged(self):
        self.assertEqual(resolve_model_path(__file__), os.path.abspath(__file__))

    def test_path_with_separator_not_searched(self):
        p = os.path.join(os.path.dirname(__file__), "does-not-exist.ts")
        self.assertEqual(resolve_model_path(p, worker_dir=self.tmp), p)

    def test_bare_name_found_in_models_dir(self):
        self.assertEqual(
            resolve_model_path("mymodel.ts", worker_dir=self.tmp),
            os.path.abspath(os.path.join(self.tmp, "models", "mymodel.ts")))

    def test_bare_name_found_in_worker_dir(self):
        with open(os.path.join(self.tmp, "rootmodel.ts"), "w") as f:
            f.write("fake")
        self.assertEqual(
            resolve_model_path("rootmodel.ts", worker_dir=self.tmp),
            os.path.abspath(os.path.join(self.tmp, "rootmodel.ts")))

    def test_bare_name_without_extension_found(self):
        # "musicnet" (no .ts) resolves to <pkg>/models/musicnet.ts
        self.assertEqual(
            resolve_model_path("mymodel", worker_dir=self.tmp),
            os.path.abspath(os.path.join(self.tmp, "models", "mymodel.ts")))

    def test_bare_name_not_found_unchanged(self):
        self.assertEqual(
            resolve_model_path("nonexistent_model", worker_dir=self.tmp),
            "nonexistent_model")


class TestDetectModelType(unittest.TestCase):
    def test_rave_detected(self):
        self.assertEqual(detect_model_type(FakeRaveModel()), "RAVE")

    def test_unknown(self):
        # str(object()) is non-empty but matches no known type -> TorchScript
        self.assertEqual(detect_model_type(object()), "TorchScript")


class TestLabelsAndAttributes(unittest.TestCase):
    def setUp(self):
        self.model = FakeRaveModel()

    def test_decode_labels(self):
        il, ol = get_method_labels(self.model, "decode")
        self.assertEqual(len(il), 16)
        self.assertIn("Latent dimension 1", il[0])
        self.assertEqual(ol, ["(signal) Channel 1"])

    def test_missing_labels(self):
        il, ol = get_method_labels(self.model, "forward")
        self.assertIsNone(il)
        self.assertIsNone(ol)

    def test_model_attributes_scan(self):
        attrs = detect_model_attributes(self.model)
        self.assertEqual(attrs["sample_rate"], 44100.0)
        self.assertNotIn("latent_mean", attrs)  # too large -> skipped

    def test_method_attributes_empty(self):
        self.assertEqual(get_method_attributes(self.model, MUSICNET_PARAMS), {})


class TestCollectModelInfo(unittest.TestCase):
    def setUp(self):
        self.model = FakeRaveModel()
        self.path = __file__

    def test_layout_and_methods(self):
        info = collect_model_info(self.model, self.path)
        self.assertEqual(info["model_type"], "RAVE")
        self.assertEqual(set(info["methods"]),
                         {"decode", "encode", "forward", "prior"})
        self.assertEqual(info["layout"]["block_size"], 2048)
        self.assertEqual(info["layout"]["channels_in"], 16)
        self.assertEqual(info["layout"]["channels_out"], 16)
        self.assertEqual(info["params"]["decode"], [16, 2048, 1, 1])
        self.assertIn("sample_rate", info["attributes"])


class TestPrintInfoBlock(unittest.TestCase):
    def test_block_contains_expected_lines(self):
        info = {
            "model_path": r"D:\AI-Models\ts models\musicnet.ts",
            "model_type": "RAVE",
            "model_size_mb": 226.01,
            "load_time_ms": 44.4,
            "methods": ["decode", "encode", "forward", "prior"],
            "params": {"decode": [16, 2048, 1, 1], "encode": [1, 1, 16, 2048],
                       "forward": [1, 1, 1, 1], "prior": [1, 2048, 16, 2048]},
            "attributes": {},
            "method_attributes": {},
            "labels": {},
            "layout": {"block_size": 2048, "channels_in": 16,
                       "channels_out": 16},
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_info_block(info)
        out = buf.getvalue()
        self.assertIn("MABJSON {", out)
        self.assertIn("MAB_INFO_BEGIN", out)
        self.assertIn("MAB_INFO_END", out)
        self.assertIn("model_type: RAVE", out)
        self.assertIn("block_size: 2048", out)
        self.assertIn("channels_in: 16", out)
        self.assertIn("channels_out: 16", out)
        self.assertIn("latent_size: 16", out)
        self.assertIn("methods: decode; encode; forward; prior", out)
        self.assertIn("param decode: 16 2048 1 1", out)
        self.assertIn("attributes: -", out)

    def test_error_block(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_info_block({"error": "boom", "model_path": "x"})
        out = buf.getvalue()
        self.assertIn("MAB_INFO_BEGIN", out)
        self.assertIn("error: boom", out)
        self.assertIn("MAB_INFO_END", out)


if __name__ == '__main__':
    unittest.main()
