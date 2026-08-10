#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unit tests for model block size extraction.

Tests:
- extract_block_size function with various model types
- Block size validation
- Fallback behavior when block size cannot be determined
"""

import unittest
import sys
import os

# Add the workspace root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the module under test
from inference_worker import extract_block_size, MAGIC_NUMBER, SharedMemoryHeader


class TestExtractBlockSize(unittest.TestCase):
    """Test the extract_block_size function."""
    
    def test_returns_zero_for_none(self):
        """Test that extract_block_size returns 0 for None model."""
        result = extract_block_size(None)
        self.assertEqual(result, 0)
    
    def test_returns_zero_for_object_without_graph(self):
        """Test that extract_block_size returns 0 for objects without graph."""
        class FakeModel:
            pass
        
        result = extract_block_size(FakeModel())
        self.assertEqual(result, 0)
    
    def test_returns_zero_for_object_without_parameters(self):
        """Test that extract_block_size returns 0 for objects without parameters."""
        class FakeModel:
            def parameters(self):
                return []
        
        result = extract_block_size(FakeModel())
        self.assertEqual(result, 0)


class TestMagicNumber(unittest.TestCase):
    """Test the magic number constant."""
    
    def test_magic_number_value(self):
        """Test that magic number is correct."""
        self.assertEqual(MAGIC_NUMBER, 0x4D414254)
    
    def test_magic_number_hex(self):
        """Test that magic number hex representation is correct."""
        self.assertEqual(hex(MAGIC_NUMBER), '0x4d414254')


class TestSharedMemoryHeaderPython(unittest.TestCase):
    """Test the Python SharedMemoryHeader structure (v2)."""
    
    def test_header_has_control_offset(self):
        """Test that the header has a control_offset field."""
        import ctypes
        field_names = [f[0] for f in SharedMemoryHeader._fields_]
        self.assertIn('control_offset', field_names)
    
    def test_header_field_count(self):
        """Test that the header has the correct number of fields."""
        import ctypes
        # Version 2 has 17 fields: magic, version, block_size, num_channels,
        # channels_in, channels_out, latent_size, input_ratio, output_ratio,
        # method[64], input_offset, output_offset, control_offset,
        # is_input_ready, is_output_ready, is_python_ready, shutdown_flag
        self.assertEqual(len(SharedMemoryHeader._fields_), 17)
    
    def test_header_has_method_fields(self):
        """Test that the header exposes the method-aware fields."""
        import ctypes
        field_names = [f[0] for f in SharedMemoryHeader._fields_]
        for name in ('channels_in', 'channels_out', 'latent_size',
                     'input_ratio', 'output_ratio', 'method'):
            self.assertIn(name, field_names)
    
    def test_header_size(self):
        """Test that the header size matches C++ (128 bytes)."""
        import ctypes
        self.assertEqual(ctypes.sizeof(SharedMemoryHeader), 128)
    
    def test_header_offsets_match_cpp(self):
        """Test that field offsets match the C++ layout."""
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


class TestControlRingBuffer(unittest.TestCase):
    """Test the ControlRingBuffer structure."""
    
    def test_control_ring_buffer_exists(self):
        """Test that ControlRingBuffer class exists."""
        from inference_worker import ControlRingBuffer, CONTROL_RING_SIZE, CONTROL_MSG_SIZE
        self.assertIsNotNone(ControlRingBuffer)
    
    def test_control_ring_size(self):
        """Test that control ring size is correct."""
        from inference_worker import CONTROL_RING_SIZE
        self.assertEqual(CONTROL_RING_SIZE, 256)
    
    def test_control_msg_size(self):
        """Test that control message size is correct."""
        from inference_worker import CONTROL_MSG_SIZE
        self.assertEqual(CONTROL_MSG_SIZE, 256)


if __name__ == '__main__':
    unittest.main()