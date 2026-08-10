#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unit tests for the nn_tilde parity work in inference_worker.py:

- Attribute type coercion (bool/int/float/str) -> _coerce_value
- Applying attributes to a real TorchScript model -> _apply_model_attribute
- Reading attributes back -> _read_model_attribute / RuntimeAttributes.get
- Listing available attributes -> _list_model_attributes
- Local model listing / delete -> list_local_models / delete_model
- Best-effort model download -> download_model (mocked HTTP)
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch

from inference_worker import (
    _coerce_value,
    _apply_model_attribute,
    _read_model_attribute,
    _list_model_attributes,
    _reapply_attributes,
    RuntimeAttributes,
    list_local_models,
    delete_model,
    download_model,
    MODEL_API_ROOT,
)


class RealMod(torch.nn.Module):
    """A torch.nn.Module that becomes a real ScriptModule (with `_c`) when
    passed to torch.jit.script() - the closest stand-in for a .ts model."""

    def __init__(self):
        super().__init__()
        self.gain = torch.jit.Attribute(1.0, float)
        self.steps = torch.jit.Attribute(3, int)
        self.name = torch.jit.Attribute("default", str)
        self.mute = torch.jit.Attribute(False, bool)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x * self.gain


def scripted():
    return torch.jit.script(RealMod())


class TestCoerceValue(unittest.TestCase):
    def test_bool_literals(self):
        for s in ("true", "1", "yes", "on", "t"):
            self.assertIs(_coerce_value(s), True)
        for s in ("false", "0", "no", "off", "f"):
            self.assertIs(_coerce_value(s), False)

    def test_int_float_str_fallback(self):
        self.assertEqual(_coerce_value("7"), 7)
        self.assertEqual(_coerce_value("2.5"), 2.5)
        self.assertIsInstance(_coerce_value("2.5"), float)
        self.assertEqual(_coerce_value("hello"), "hello")

    def test_typed_float(self):
        self.assertEqual(_coerce_value("2.5", current=1.0), 2.5)
        self.assertEqual(_coerce_value("2", current=1.0), 2.0)

    def test_typed_int(self):
        self.assertEqual(_coerce_value("7", current=3), 7)
        self.assertEqual(_coerce_value("2.5", current=3), 2)  # int(float(...))

    def test_typed_bool(self):
        self.assertIs(_coerce_value("true", current=False), True)
        self.assertIs(_coerce_value("0", current=True), False)

    def test_typed_str_untouched(self):
        self.assertEqual(_coerce_value("2.5", current="abc"), "2.5")


class TestApplyModelAttribute(unittest.TestCase):
    def setUp(self):
        self.model = scripted()

    def test_float_attr(self):
        ok, val = _apply_model_attribute(self.model, "gain", "2.5")
        self.assertTrue(ok)
        self.assertEqual(val, 2.5)
        self.assertEqual(self.model.gain, 2.5)
        self.assertEqual(self.model._c.getattr("gain"), 2.5)

    def test_int_attr(self):
        ok, val = _apply_model_attribute(self.model, "steps", "7")
        self.assertTrue(ok)
        self.assertEqual(val, 7)
        self.assertEqual(self.model._c.getattr("steps"), 7)

    def test_bool_attr(self):
        ok, val = _apply_model_attribute(self.model, "mute", "true")
        self.assertTrue(ok)
        self.assertIs(val, True)
        self.assertIs(self.model._c.getattr("mute"), True)

    def test_unknown_attr_fails_on_scriptmodule(self):
        ok, val = _apply_model_attribute(self.model, "nope", "1")
        self.assertFalse(ok)
        self.assertIsInstance(val, str)

    def test_unknown_attr_does_not_raise_on_plain_object(self):
        class Anything:
            def __setattr__(self, name, value):
                object.__setattr__(self, name, value)

        ok, val = _apply_model_attribute(Anything(), "nope", "1")
        # must never raise; result may be True (permissive) or False
        self.assertIsInstance(ok, bool)

    def test_no_model(self):
        ok, val = _apply_model_attribute(None, "gain", "1")
        self.assertFalse(ok)


class TestReadListReapply(unittest.TestCase):
    def setUp(self):
        self.model = scripted()
        self.attrs = RuntimeAttributes()

    def test_read_model_attribute(self):
        self.assertEqual(_read_model_attribute(self.model, "gain"), 1.0)
        self.assertEqual(_read_model_attribute(self.model, "nope"), None)

    def test_list_model_attributes(self):
        names = _list_model_attributes(self.model, self.attrs)
        # gain wird in forward referenziert -> ueber Code-Scan + hasattr-Probe
        self.assertIn("gain", names)
        # runtime-gestored names erscheinen immer
        self.attrs.set("user_knob", "5", model=self.model)
        names = _list_model_attributes(self.model, self.attrs)
        self.assertIn("user_knob", names)

    def test_reapply(self):
        _apply_model_attribute(self.model, "gain", "9.0")
        self.attrs.set("gain", 9.0, model=self.model)
        # Simulate a fresh reload: same runtime attrs, new model instance
        fresh = scripted()
        _reapply_attributes(fresh, self.attrs)
        self.assertEqual(fresh.gain, 9.0)


class TestRuntimeAttributes(unittest.TestCase):
    def test_set_get_cached(self):
        a = RuntimeAttributes()
        a.set("my_attr", "5", model=None)
        self.assertEqual(a.get("my_attr"), 5)

    def test_get_falls_back_to_model(self):
        a = RuntimeAttributes()
        self.assertEqual(a.get("gain", model=scripted()), 1.0)

    def test_apply_to_model_stores_coerced(self):
        a = RuntimeAttributes()
        m = scripted()
        msg = a.set("gain", "3.25", model=m)
        self.assertIn("3.25", msg)
        self.assertEqual(m.gain, 3.25)
        self.assertEqual(a.get("gain"), 3.25)


class TestLocalModels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        models = os.path.join(self.tmp.name, "models")
        os.makedirs(models)
        self.ts = os.path.join(models, "demo.ts")
        with open(self.ts, "wb") as f:
            f.write(b"placeholder")
        # inference_worker resolves the package as <worker_dir>/.. ; put the
        # models dir next to the fake worker dir.
        self.fake_worker_dir = os.path.join(self.tmp.name, "worker")
        os.makedirs(self.fake_worker_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_local_models_finds_package_models(self):
        # Use tmp/models directly (worker_dir == parent of models dir)
        found = list_local_models(worker_dir=os.path.dirname(self.ts))
        self.assertIn("demo.ts", found)

    def test_delete_model_removes_file(self):
        ok, path = delete_model("demo", worker_dir=os.path.dirname(self.ts))
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(self.ts))

    def test_delete_unknown(self):
        ok, path = delete_model("missing", worker_dir=os.path.dirname(self.ts))
        self.assertFalse(ok)


class TestDownloadModel(unittest.TestCase):
    def test_download_uses_api_and_writes_file(self):
        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"MABT" * 100

        with tempfile.TemporaryDirectory() as tmp:
            worker_dir = os.path.join(tmp, "worker")
            os.makedirs(worker_dir)
            with mock.patch("inference_worker.urllib.request.urlopen",
                            return_value=FakeResp()) as m:
                ok, path = download_model("mycard", name="my.ts",
                                          worker_dir=worker_dir)
            self.assertTrue(ok)
            self.assertTrue(os.path.isfile(path))
            url = m.call_args[0][0]
            self.assertTrue(url.startswith(MODEL_API_ROOT))
            self.assertIn("download_model?model=mycard", url)

    def test_download_reports_network_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker_dir = os.path.join(tmp, "worker")
            os.makedirs(worker_dir)
            with mock.patch("inference_worker.urllib.request.urlopen",
                            side_effect=OSError("offline")):
                ok, msg = download_model("card", worker_dir=worker_dir)
            self.assertFalse(ok)
            self.assertIsInstance(msg, str)


if __name__ == "__main__":
    unittest.main()
