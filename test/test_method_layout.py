#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unit tests for the Phase 3 method-aware layout & dispatch logic.

Covers:
- get_method_params: {method}_params extraction from a TorchScript-like model
- compute_layout: block_size / max channel sizing across all methods
- infer_method: nn_tilde semantics (forward/encode/decode/prior) with a fake
  model that records the exact tensors passed to it
- Optional integration test against the real RAVE/AFTER model (skipped when
  the model file is not present)
"""

import unittest
import sys
import os
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference_worker import (
    get_method_params,
    compute_layout,
    infer_method,
)

MUSICNET_PARAMS = {
    'decode': (16, 2048, 1, 1),    # latent -> audio
    'encode': (1, 1, 16, 2048),    # audio -> latent
    'forward': (1, 1, 1, 1),
    'prior': (1, 2048, 16, 2048),  # conditioning -> latent
}


class FakeScriptedModel:
    """Mimics a TorchScript model's method surface.

    Each call is recorded in ``calls`` so tests can assert the exact tensors
    the worker passed (especially the last-sample selection for decode/prior).
    """

    def __init__(self, params=MUSICNET_PARAMS):
        self.params = params
        self.calls = []
        for name, (ci, ri, co, ro) in params.items():
            setattr(self, name + "_params", torch.tensor(
                [ci, ri, co, ro], dtype=torch.long))

    def forward(self, x):
        self.calls.append(("forward", x.clone()))
        return x

    def encode(self, x):
        self.calls.append(("encode", x.clone()))
        return torch.zeros(x.size(0), 16, 1)

    def decode(self, z):
        self.calls.append(("decode", z.clone()))
        return torch.zeros(z.size(0), 1, 2048)

    def prior(self, z):
        self.calls.append(("prior", z.clone()))
        return torch.zeros(z.size(0), 16, 1)


class TestGetMethodParams(unittest.TestCase):
    def test_extracts_all_four_methods(self):
        model = FakeScriptedModel()
        params = get_method_params(model)
        self.assertEqual(set(params.keys()), {'forward', 'encode', 'decode', 'prior'})

    def test_parses_musicnet_layout(self):
        model = FakeScriptedModel()
        params = get_method_params(model)
        self.assertEqual(params['decode'], (16, 2048, 1, 1))
        self.assertEqual(params['encode'], (1, 1, 16, 2048))
        self.assertEqual(params['forward'], (1, 1, 1, 1))
        self.assertEqual(params['prior'], (1, 2048, 16, 2048))

    def test_returns_empty_for_bare_object(self):
        self.assertEqual(get_method_params(object()), {})

    def test_skips_method_without_params(self):
        class Partial:
            def forward(self, x):
                return x

            def encode(self, x):
                return x
        model = Partial()
        params = get_method_params(model)
        # heuristic detection finds forward/encode/decode/prior but only
        # methods with *_params attributes are collected
        self.assertEqual(params, {})


class TestComputeLayout(unittest.TestCase):
    def test_block_size_covers_max_ratio(self):
        block_size, max_in, max_out = compute_layout(MUSICNET_PARAMS, 512)
        self.assertEqual(block_size, 2048)

    def test_respects_larger_requested_bufsize(self):
        block_size, _, _ = compute_layout(MUSICNET_PARAMS, 8192)
        self.assertEqual(block_size, 8192)

    def test_max_channels_over_all_methods(self):
        _, max_in, max_out = compute_layout(MUSICNET_PARAMS, 512)
        self.assertEqual(max_in, 16)   # decode latent in
        self.assertEqual(max_out, 16)  # encode/prior latent out

    def test_empty_params_uses_requested_size(self):
        block_size, max_in, max_out = compute_layout({}, 1024)
        self.assertEqual((block_size, max_in, max_out), (1024, 1, 1))


class TestInferMethodSemantics(unittest.TestCase):
    def setUp(self):
        self.model = FakeScriptedModel()
        self.device = torch.device('cpu')

    def test_forward_feeds_full_block(self):
        inp = np.random.randn(1, 2048).astype(np.float32)
        out = infer_method(self.model, self.device, 'forward',
                           MUSICNET_PARAMS, inp)
        self.assertEqual(out.shape, (1, 2048))
        name, x = self.model.calls[0]
        self.assertEqual(name, 'forward')
        self.assertEqual(x.shape, (1, 1, 2048))
        np.testing.assert_array_almost_equal(out, inp)

    def test_encode_holds_latent_frames(self):
        inp = np.random.randn(1, 2048).astype(np.float32)
        out = infer_method(self.model, self.device, 'encode',
                           MUSICNET_PARAMS, inp)
        self.assertEqual(out.shape, (16, 2048))
        name, x = self.model.calls[0]
        self.assertEqual(name, 'encode')
        self.assertEqual(x.shape, (1, 1, 2048))

    def test_decode_takes_last_sample_per_channel(self):
        inp = np.random.randn(16, 2048).astype(np.float32)
        out = infer_method(self.model, self.device, 'decode',
                           MUSICNET_PARAMS, inp)
        self.assertEqual(out.shape, (1, 2048))
        name, z = self.model.calls[0]
        self.assertEqual(name, 'decode')
        self.assertEqual(z.shape, (1, 16, 1))
        # The last sample of each channel must be passed to the model
        np.testing.assert_array_almost_equal(z[0, :, 0].numpy(), inp[:, -1])

    def test_prior_takes_last_conditioning_sample(self):
        inp = np.random.randn(1, 2048).astype(np.float32)
        out = infer_method(self.model, self.device, 'prior',
                           MUSICNET_PARAMS, inp)
        self.assertEqual(out.shape, (16, 2048))
        name, z = self.model.calls[0]
        self.assertEqual(name, 'prior')
        self.assertEqual(z.shape, (1, 1, 1))
        np.testing.assert_array_almost_equal(z[0, 0, 0].numpy(), inp[0, -1])

    def test_output_trims_extra_samples(self):
        class LongOutput(FakeScriptedModel):
            def decode(self, z):
                self.calls.append(("decode", z.clone()))
                return torch.zeros(z.size(0), 1, 4096)
        model = LongOutput()
        inp = np.random.randn(16, 2048).astype(np.float32)
        out = infer_method(model, self.device, 'decode', MUSICNET_PARAMS, inp)
        self.assertEqual(out.shape, (1, 2048))


class TestInferMethodBatched(unittest.TestCase):
    """Phase 6 (mcs.mab~): 3-D input (n_batches, ci, block) is fed through the
    model in ONE batched forward pass and returns (n_batches, co, block)."""

    def setUp(self):
        self.model = FakeScriptedModel()
        self.device = torch.device('cpu')

    def test_forward_batched_keeps_batch_dim(self):
        inp = np.random.randn(4, 1, 2048).astype(np.float32)
        out = infer_method(self.model, self.device, 'forward',
                           MUSICNET_PARAMS, inp)
        self.assertEqual(out.shape, (4, 1, 2048))
        name, x = self.model.calls[0]
        self.assertEqual(name, 'forward')
        self.assertEqual(x.shape, (4, 1, 2048))
        np.testing.assert_array_almost_equal(out, inp)

    def test_encode_batched(self):
        inp = np.random.randn(4, 1, 2048).astype(np.float32)
        out = infer_method(self.model, self.device, 'encode',
                           MUSICNET_PARAMS, inp)
        self.assertEqual(out.shape, (4, 16, 2048))
        name, x = self.model.calls[0]
        self.assertEqual(name, 'encode')
        self.assertEqual(x.shape, (4, 1, 2048))

    def test_decode_batched_takes_last_sample_per_channel(self):
        inp = np.random.randn(4, 16, 2048).astype(np.float32)
        out = infer_method(self.model, self.device, 'decode',
                           MUSICNET_PARAMS, inp)
        self.assertEqual(out.shape, (4, 1, 2048))
        name, z = self.model.calls[0]
        self.assertEqual(name, 'decode')
        self.assertEqual(z.shape, (4, 16, 1))
        # last sample of each (batch, channel) must be passed to the model
        np.testing.assert_array_almost_equal(z[:, :, 0].numpy(), inp[:, :, -1])

    def test_prior_batched(self):
        inp = np.random.randn(4, 1, 2048).astype(np.float32)
        out = infer_method(self.model, self.device, 'prior',
                           MUSICNET_PARAMS, inp)
        self.assertEqual(out.shape, (4, 16, 2048))
        name, z = self.model.calls[0]
        self.assertEqual(name, 'prior')
        self.assertEqual(z.shape, (4, 1, 1))
        np.testing.assert_array_almost_equal(z[:, 0, 0].numpy(), inp[:, 0, -1])

    def test_batched_output_trims_extra_samples(self):
        class LongOutput(FakeScriptedModel):
            def decode(self, z):
                self.calls.append(("decode", z.clone()))
                return torch.zeros(z.size(0), 1, 4096)
        model = LongOutput()
        inp = np.random.randn(4, 16, 2048).astype(np.float32)
        out = infer_method(model, self.device, 'decode', MUSICNET_PARAMS, inp)
        self.assertEqual(out.shape, (4, 1, 2048))


MODEL_PATH = r"D:\AI-Models\ts models\musicnet.ts"


@unittest.skipUnless(os.path.exists(MODEL_PATH),
                     "RAVE/AFTER test model not present")
class TestRealModelDispatch(unittest.TestCase):
    """Integration check of the dispatch against the real AFTER model."""

    @classmethod
    def setUpClass(cls):
        cls.model = torch.jit.load(MODEL_PATH, map_location='cpu').eval()
        cls.device = torch.device('cpu')
        cls.params = get_method_params(cls.model)

    def test_params_match_musicnet(self):
        self.assertEqual(self.params['decode'], (16, 2048, 1, 1))
        self.assertEqual(self.params['encode'], (1, 1, 16, 2048))
        self.assertEqual(self.params['forward'], (1, 1, 1, 1))
        self.assertEqual(self.params['prior'], (1, 2048, 16, 2048))

    def test_real_decode_shapes(self):
        inp = np.random.randn(16, 2048).astype(np.float32)
        out = infer_method(self.model, self.device, 'decode',
                           self.params, inp)
        self.assertEqual(out.shape, (1, 2048))
        self.assertTrue(np.all(np.isfinite(out)))

    def test_real_encode_shapes(self):
        inp = np.random.randn(1, 2048).astype(np.float32)
        out = infer_method(self.model, self.device, 'encode',
                           self.params, inp)
        self.assertEqual(out.shape, (16, 2048))
        self.assertTrue(np.all(np.isfinite(out)))

    def test_real_forward_shapes(self):
        inp = np.random.randn(1, 2048).astype(np.float32)
        out = infer_method(self.model, self.device, 'forward',
                           self.params, inp)
        self.assertEqual(out.shape, (1, 2048))
        self.assertTrue(np.all(np.isfinite(out)))

    def test_real_prior_shapes(self):
        inp = np.random.randn(1, 2048).astype(np.float32)
        out = infer_method(self.model, self.device, 'prior',
                           self.params, inp)
        self.assertEqual(out.shape, (16, 2048))
        self.assertTrue(np.all(np.isfinite(out)))


if __name__ == '__main__':
    unittest.main()
