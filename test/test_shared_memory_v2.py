#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unit tests for the Phase 3 SharedMemoryHeader v2 (method-aware metadata).

Verifies that the real ctypes header layout matches the C++ struct (128 bytes,
field offsets) and that SharedMemoryManager.apply_method() publishes the active
method layout (method / channels / ratios / latent size) that C++ reads to
rebuild inlets and outlets.
"""

import unittest
import sys
import os
import ctypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference_worker import SharedMemoryHeader, SharedMemoryManager

MUSICNET_PARAMS = {
    'decode': (16, 2048, 1, 1),    # latent -> audio
    'encode': (1, 1, 16, 2048),    # audio -> latent
    'forward': (1, 1, 1, 1),
    'prior': (1, 2048, 16, 2048),  # conditioning -> latent
}


class TestHeaderLayoutV2(unittest.TestCase):
    def test_header_size_is_128(self):
        self.assertEqual(ctypes.sizeof(SharedMemoryHeader), 128)

    def test_field_offsets_match_cpp(self):
        # Field offsets asserted by test_shared_memory_header_compatibility.cpp
        self.assertEqual(SharedMemoryHeader.magic.offset, 0)
        self.assertEqual(SharedMemoryHeader.version.offset, 4)
        self.assertEqual(SharedMemoryHeader.block_size.offset, 8)
        self.assertEqual(SharedMemoryHeader.num_channels.offset, 12)
        self.assertEqual(SharedMemoryHeader.channels_in.offset, 16)
        self.assertEqual(SharedMemoryHeader.channels_out.offset, 20)
        self.assertEqual(SharedMemoryHeader.latent_size.offset, 24)
        self.assertEqual(SharedMemoryHeader.input_ratio.offset, 28)
        self.assertEqual(SharedMemoryHeader.output_ratio.offset, 32)
        self.assertEqual(SharedMemoryHeader.method.offset, 36)
        self.assertEqual(SharedMemoryHeader.input_offset.offset, 100)
        self.assertEqual(SharedMemoryHeader.output_offset.offset, 104)
        self.assertEqual(SharedMemoryHeader.control_offset.offset, 108)
        self.assertEqual(SharedMemoryHeader.is_input_ready.offset, 112)
        self.assertEqual(SharedMemoryHeader.is_output_ready.offset, 116)
        self.assertEqual(SharedMemoryHeader.is_python_ready.offset, 120)
        self.assertEqual(SharedMemoryHeader.shutdown_flag.offset, 124)

    def test_flags_are_c_long(self):
        # Must be c_long, not c_bool: C++ uses `long` + InterlockedExchange
        self.assertIs(SharedMemoryHeader.is_input_ready.type, ctypes.c_long)
        self.assertIs(SharedMemoryHeader.shutdown_flag.type, ctypes.c_long)


def _manager_with_header():
    mgr = SharedMemoryManager(
        shm_name="MabSharedMem_DEADBEEF",
        ready_event_name="MabReadyEvent_DEADBEEF",
        block_size=2048, channels_in=16, channels_out=16)
    mgr._p_header = SharedMemoryHeader()
    return mgr


class TestApplyMethod(unittest.TestCase):
    def test_decode_layout(self):
        mgr = _manager_with_header()
        mgr.apply_method("decode", MUSICNET_PARAMS)
        h = mgr._p_header
        self.assertEqual(h.method, b"decode")
        self.assertEqual(h.channels_in, 16)
        self.assertEqual(h.channels_out, 1)
        self.assertEqual(h.input_ratio, 2048)
        self.assertEqual(h.output_ratio, 1)
        self.assertEqual(h.latent_size, 16)   # = channels_in (decode/prior)

    def test_encode_layout(self):
        mgr = _manager_with_header()
        mgr.apply_method("encode", MUSICNET_PARAMS)
        h = mgr._p_header
        self.assertEqual(h.method, b"encode")
        self.assertEqual(h.channels_in, 1)
        self.assertEqual(h.channels_out, 16)
        self.assertEqual(h.input_ratio, 1)
        self.assertEqual(h.output_ratio, 2048)
        self.assertEqual(h.latent_size, 16)  # = channels_out (encode)

    def test_forward_layout(self):
        mgr = _manager_with_header()
        mgr.apply_method("forward", MUSICNET_PARAMS)
        h = mgr._p_header
        self.assertEqual(h.method, b"forward")
        self.assertEqual(h.channels_in, 1)
        self.assertEqual(h.channels_out, 1)
        self.assertEqual(h.latent_size, 0)

    def test_unknown_method_is_noop(self):
        mgr = _manager_with_header()
        mgr.apply_method("bogus", MUSICNET_PARAMS)
        h = mgr._p_header
        # apply_method returns early; header keeps its zero-initialized state
        self.assertEqual(h.method, b"")
        self.assertEqual(h.channels_in, 0)

    def test_no_params_is_noop(self):
        mgr = _manager_with_header()
        mgr.apply_method("forward", {})
        self.assertEqual(mgr._p_header.method, b"")


if __name__ == '__main__':
    unittest.main()
