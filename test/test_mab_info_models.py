#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T2 – mab.info-Integrationstests (Offline, ohne Max Runtime) – Kategorie C.

Ruft `query_model()` fuer jedes TorchScript-Modell aus D:\\AI-Models\\ts models
einzeln auf, parst den stdout-Block und validiert Struktur/JSON-Felder.

JEDES MODELL HAT SEINE EIGENE TEST-METHODE → saubere Trennung, kein
kumulativer Speicherdruck. Dynamisch via setattr() generiert.

AUSGESCHLOSSEN: `darbouka_onnx.ts` (ONNX, kein TorchScript).

Zusaetzlich: echter CLI-Subprozess-Test gegen musicnet.ts.
"""

import gc
import glob
import io
import json
import os
import re
import subprocess
import sys
import unittest
from contextlib import redirect_stdout

import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference_worker import query_model

MODEL_DIR = r"D:\AI-Models\ts models"
WORKER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "inference_worker.py")

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


def run_query(path):
    buf = io.StringIO()
    code = None
    with redirect_stdout(buf):
        try:
            query_model(path)
        except SystemExit as exc:
            code = exc.code if exc.code is not None else 0
    return buf.getvalue(), code


def parse_info_block(text):
    lines = text.splitlines()
    parsed = {}
    in_block = False
    for ln in lines:
        if ln.strip() == "MAB_INFO_BEGIN":
            in_block = True
            continue
        if ln.strip() == "MAB_INFO_END":
            break
        if in_block and ":" in ln:
            key, _, value = ln.partition(":")
            parsed[key.strip()] = value.strip()
    return parsed


# ---------------------------------------------------------------------------
# query_model – ein Test pro Modell (exit 0 + Block-Rahmen)
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(MODEL_DIR),
                     "Model directory not found: D:\\AI-Models\\ts models")
class TestQueryModel(unittest.TestCase):
    """query_model() pro Modell einzeln: exit 0 + MAB_INFO_BEGIN/END."""


def _make_query_test(path):
    def test(self):
        kwargs = {"model_path": path}
        text, code = run_query(path)
        self.assertEqual(code, 0, "exit=%s for %s" % (code, path))
        self.assertIn("MAB_INFO_BEGIN", text)
        self.assertIn("MAB_INFO_END", text)
        self.assertNotIn("\nerror:", "\n" + text)
        _cleanup()
    return test


for _path in model_files():
    _name = _safe_name(os.path.basename(_path))
    setattr(TestQueryModel, f'test_query_{_name}',
            _make_query_test(_path))


# ---------------------------------------------------------------------------
# Info-Block-Felder – ein Test pro Modell
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(MODEL_DIR),
                     "Model directory not found: D:\\AI-Models\\ts models")
class TestInfoBlockFields(unittest.TestCase):
    """Pflichtfelder des MAB_INFO-Blocks pro Modell einzeln."""


def _make_block_fields_test(path):
    def test(self):
        text, code = run_query(path)
        self.assertEqual(code, 0)
        parsed = parse_info_block(text)
        self.assertIn("model_path", parsed)
        self.assertIn("model_type", parsed)
        self.assertIn("block_size", parsed)
        self.assertIn("channels_in", parsed)
        self.assertIn("channels_out", parsed)
        self.assertIn("latent_size", parsed)
        self.assertIn("methods", parsed)
        self.assertIn("attributes", parsed)
        self.assertGreaterEqual(int(parsed["block_size"]), 1)
        self.assertGreaterEqual(int(parsed["channels_in"]), 1)
        self.assertGreaterEqual(int(parsed["channels_out"]), 1)
        self.assertGreaterEqual(int(parsed["latent_size"]), 1)
        self.assertIn(parsed["model_type"],
                      ("RAVE", "AFTER", "MusicNet", "TorchScript"))
        methods = [m for m in parsed["methods"].split("; ") if m]
        for m in methods:
            key = "param " + m
            self.assertIn(key, parsed)
            vals = parsed[key].split()
            self.assertEqual(len(vals), 4)
            for v in vals:
                self.assertGreaterEqual(int(v), 1)
        _cleanup()
    return test


for _path in model_files():
    _name = _safe_name(os.path.basename(_path))
    setattr(TestInfoBlockFields, f'test_block_fields_{_name}',
            _make_block_fields_test(_path))


# ---------------------------------------------------------------------------
# MABJSON – ein Test pro Modell
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(MODEL_DIR),
                     "Model directory not found: D:\\AI-Models\\ts models")
class TestInfoJson(unittest.TestCase):
    """MABJSON-Zeile muss gueltiges JSON pro Modell sein."""


def _make_json_test(path):
    def test(self):
        text, code = run_query(path)
        self.assertEqual(code, 0)
        json_line = [ln for ln in text.splitlines()
                     if ln.startswith("MABJSON ")]
        self.assertEqual(len(json_line), 1)
        data = json.loads(json_line[0][len("MABJSON "):])
        for key in ("model_path", "model_type", "methods", "params", "layout"):
            self.assertIn(key, data)
        self.assertIsInstance(data["methods"], list)
        self.assertIsInstance(data["params"], dict)
        self.assertIn("block_size", data["layout"])
        self.assertIn("channels_in", data["layout"])
        self.assertIn("channels_out", data["layout"])
        self.assertFalse(data.get("error"))
        _cleanup()
    return test


for _path in model_files():
    _name = _safe_name(os.path.basename(_path))
    setattr(TestInfoJson, f'test_json_{_name}',
            _make_json_test(_path))


# ---------------------------------------------------------------------------
# musicnet.ts – bekannte Werte (statisch, ein Modell)
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(os.path.join(MODEL_DIR, "musicnet.ts")),
                     "musicnet.ts not present")
class TestInfoBlockMusicnet(unittest.TestCase):
    def test_musicnet_known_values(self):
        path = os.path.join(MODEL_DIR, "musicnet.ts")
        text, code = run_query(path)
        self.assertEqual(code, 0)
        parsed = parse_info_block(text)
        self.assertEqual(parsed["model_type"], "RAVE")
        self.assertEqual(parsed["block_size"], "2048")
        self.assertEqual(parsed["latent_size"], "16")
        self.assertEqual(parsed["methods"],
                         "decode; encode; forward; prior")
        self.assertEqual(parsed["param decode"], "16 2048 1 1")
        self.assertEqual(parsed["param encode"], "1 1 16 2048")
        self.assertEqual(parsed["param prior"], "1 2048 16 2048")
        _cleanup()


# ---------------------------------------------------------------------------
# CLI-End-to-End (Subprozess, isoliert)
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.exists(os.path.join(MODEL_DIR, "musicnet.ts")),
                     "musicnet.ts not present")
class TestQueryCliEndToEnd(unittest.TestCase):
    def test_cli_query_musicnet(self):
        model = os.path.join(MODEL_DIR, "musicnet.ts")
        proc = subprocess.run(
            [sys.executable, WORKER, "--query", model],
            capture_output=True, text=True, timeout=180)
        self.assertEqual(proc.returncode, 0,
                         "stderr: %s" % proc.stderr[-500:])
        out = proc.stdout
        self.assertIn("MAB_INFO_BEGIN", out)
        self.assertIn("MAB_INFO_END", out)
        self.assertIn("model_type: RAVE", out)
        self.assertIn("block_size: 2048", out)
        self.assertIn("param decode: 16 2048 1 1", out)

    def test_cli_query_missing_model_exits_nonzero(self):
        proc = subprocess.run(
            [sys.executable, WORKER, "--query", "definitely_missing_model.ts"],
            capture_output=True, text=True, timeout=120)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("error:", proc.stdout)
        self.assertIn("MAB_INFO_BEGIN", proc.stdout)
        self.assertIn("MAB_INFO_END", proc.stdout)


if __name__ == "__main__":
    unittest.main()
