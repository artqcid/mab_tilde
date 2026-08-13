#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unit tests for the SharedMemoryHeader v4 (Bug 11 ring buffer + Bug 12
max_channels_in/out) - method-aware metadata + MC channel_map.

Verifies that the real ctypes header layout matches the C++ struct (204 bytes,
field offsets) and that SharedMemoryManager.apply_method() publishes the active
method layout (method / channels / ratios / latent size) that C++ reads to
rebuild inlets and outlets.
"""

import unittest
import sys
import os
import ctypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference_worker import SharedMemoryHeader, SharedMemoryManager, _method_id

MUSICNET_PARAMS = {
    'decode': (16, 2048, 1, 1),    # latent -> audio
    'encode': (1, 1, 16, 2048),    # audio -> latent
    'forward': (1, 1, 1, 1),
    'prior': (1, 2048, 16, 2048),  # conditioning -> latent
}


class TestHeaderLayoutV2(unittest.TestCase):
    def test_header_size_is_204(self):
        self.assertEqual(ctypes.sizeof(SharedMemoryHeader), 268)

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
        self.assertEqual(SharedMemoryHeader.method_id.offset, 88)
        self.assertEqual(SharedMemoryHeader.input_offset.offset, 92)
        self.assertEqual(SharedMemoryHeader.output_offset.offset, 96)
        self.assertEqual(SharedMemoryHeader.control_offset.offset, 100)
        # Bug 11 (ring v4): ring_blocks + 4 ring head/tail counters replace
        # the old input_buffer_index/output_buffer_index ping-pong indices.
        self.assertEqual(SharedMemoryHeader.ring_blocks.offset, 104)
        self.assertEqual(SharedMemoryHeader.in_write_head.offset, 108)
        self.assertEqual(SharedMemoryHeader.in_read_tail.offset, 112)
        self.assertEqual(SharedMemoryHeader.out_write_head.offset, 116)
        self.assertEqual(SharedMemoryHeader.out_read_tail.offset, 120)
        # Bug 12: constant ring-block channel capacity (max across methods).
        self.assertEqual(SharedMemoryHeader.max_channels_in.offset, 124)
        self.assertEqual(SharedMemoryHeader.max_channels_out.offset, 128)
        # Phase 5: channel_map follows the max-channel fields
        self.assertEqual(SharedMemoryHeader.channel_map.offset, 132)
        self.assertEqual(ctypes.sizeof(SharedMemoryHeader.channel_map.type),
                         32 * ctypes.sizeof(ctypes.c_uint32))
        self.assertEqual(SharedMemoryHeader.is_python_ready.offset, 260)
        self.assertEqual(SharedMemoryHeader.shutdown_flag.offset, 264)

    def test_flags_are_c_long(self):
        # Must be c_long, not c_bool: C++ uses `long` + InterlockedExchange
        self.assertIs(SharedMemoryHeader.is_python_ready.type, ctypes.c_long)
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
        self.assertEqual(h.method_id, _method_id("decode"))
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
        self.assertEqual(h.method_id, _method_id("encode"))
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
        self.assertEqual(h.method_id, _method_id("forward"))
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


class TestRingBlockStrideBug12(unittest.TestCase):
    """Bug 12 regression: the ring-block byte stride (spacing between
    consecutive ring slots in the SHM) MUST be derived from the constant
    max_channels_in/out fields, never from the active channels_in/out that
    apply_method() overwrites per method.

    Buffers are allocated ONCE at SharedMemoryManager.__init__ time, sized
    for the maximum channel count across all methods (channels_in/out ctor
    args below == max, per compute_layout() in main()). Real RAVE/AFTER
    models typically declare forward=(1,1,1,1) but decode=(z_dim,r,1,1) and
    encode=(1,r,z_dim,1) - i.e. active channels_out for decode (1) is
    smaller than the SHM's allocated max_channels_out (z_dim), and it was
    exactly this active/max mismatch that silently misaligned every ring
    slot after index 0 (C++ read stale/zero memory), producing one correct
    output block followed by permanent silence.
    """

    def test_output_stride_uses_max_not_active_channels(self):
        mgr = SharedMemoryManager(
            shm_name="MabSharedMem_Bug12Test",
            ready_event_name="MabReadyEvent_Bug12Test",
            block_size=2048, channels_in=16, channels_out=16)
        mgr._p_header = SharedMemoryHeader()
        mgr._p_header.max_channels_in = mgr.channels_in
        mgr._p_header.max_channels_out = mgr.channels_out
        mgr.apply_method("decode", MUSICNET_PARAMS)  # active co = 1
        h = mgr._p_header

        # The real per-ring-block byte size Python allocated (what C++ MUST
        # use as the stride between ring slots).
        correct_stride = int(h.max_channels_out) * mgr.block_size * 4
        self.assertEqual(correct_stride, mgr.output_size)

        # Bug 12: this is the WRONG (pre-fix) stride C++ used to compute -
        # deliberately asserted != correct_stride to document the bug this
        # test guards against regressing to.
        buggy_stride = int(h.channels_out) * mgr.block_size * 4
        self.assertNotEqual(buggy_stride, correct_stride,
                             "test fixture no longer reproduces the "
                             "active != max mismatch this guards against")
        self.assertEqual(correct_stride, mgr.channels_out * mgr.block_size * 4)

    def test_input_stride_uses_max_not_active_channels(self):
        # decode's active ci (16) happens to equal max_channels_in (16) for
        # this fixture, so also check "encode" where active ci=1 != max=16.
        mgr = SharedMemoryManager(
            shm_name="MabSharedMem_Bug12Test2",
            ready_event_name="MabReadyEvent_Bug12Test2",
            block_size=2048, channels_in=16, channels_out=16)
        mgr._p_header = SharedMemoryHeader()
        mgr._p_header.max_channels_in = mgr.channels_in
        mgr._p_header.max_channels_out = mgr.channels_out
        mgr.apply_method("encode", MUSICNET_PARAMS)  # active ci = 1
        h = mgr._p_header

        correct_stride = int(h.max_channels_in) * mgr.block_size * 4
        self.assertEqual(correct_stride, mgr.input_size)
        buggy_stride = int(h.channels_in) * mgr.block_size * 4
        self.assertNotEqual(buggy_stride, correct_stride)


class TestChannelMapPhase5(unittest.TestCase):
    """Phase 5: mc.mab~ publishes per-inlet channel counts in the header."""

    def test_read_channel_map_empty_by_default(self):
        mgr = _manager_with_header()
        self.assertEqual(mgr.read_channel_map(), [])

    def test_read_channel_map_skips_zeros(self):
        mgr = _manager_with_header()
        mgr._p_header.channel_map[0] = 16
        mgr._p_header.channel_map[2] = 2
        self.assertEqual(mgr.read_channel_map(), [16, 2])

    def test_get_total_input_channels_sums_map(self):
        mgr = _manager_with_header()
        mgr._p_header.channel_map[0] = 8
        mgr._p_header.channel_map[1] = 8
        self.assertEqual(mgr.get_total_input_channels(), 16)

    def test_get_total_falls_back_to_channels_in(self):
        # Mono mode: C++ never writes channel_map -> header->channels_in
        mgr = _manager_with_header()
        mgr._p_header.channels_in = 16
        self.assertEqual(mgr.get_total_input_channels(), 16)


if __name__ == '__main__':
    unittest.main()
