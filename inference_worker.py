#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
inference_worker.py

A lock-free, process-isolated backend for MaxMSP objects `mab~`, `mc.mab~` and
`mcs.mab~`. It creates shared memory and signals C++ to attach, then exchanges
audio blocks via Windows shared memory with a lock-free SPSC ring buffer for
control messages.

Features
--------
* Creates shared memory with handshake protocol (Python creates, C++ opens)
* Loads a TorchScript model (.ts) once and keeps it alive.
* Switches between CPU and CUDA automatically (`gpu` flag).
* Supports dynamic reload of the model (`reload` message).
* Emits a full model dump (`dump` message) to the Max console.
* Allows runtime attribute modification (`set <attr> <value...>`).
* Uses a single-producer / single-consumer ring buffer for messages – no Python
  `queue` overhead, fully lock-free.
* Multi-channel support with contiguous memory layout [num_channels, block_size]
* Phase 5 (mc.mab~): per-inlet channel counts via header channel_map.
* Phase 6 (mcs.mab~): batch-major layout [n_batches x channels x block_size],
  batched inference in one forward pass (view(n_batches, ci, bs)).
"""

import sys
import os
import gc
import ctypes
import struct
import time
import threading
import argparse
import traceback
import urllib.request
import urllib.parse
import numpy as np
import torch
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
#  Constants & Windows API helpers
# ---------------------------------------------------------------------------

# WinAPI constants
FILE_MAP_ALL_ACCESS = 0x00F001F
PAGE_READWRITE     = 0x04   # 0x01 wäre PAGE_NOACCESS -> CreateFileMappingW schlägt fehl (WinError 87)
ERROR_FILE_NOT_FOUND = 2
NULL = 0

# Magic number for header validation
MAGIC_NUMBER = 0x4D414254  # 'MABT'

# nn_tilde-compatible model download API (IRCAM Forum). Best-effort: all
# remote access is wrapped in try/except so the worker never crashes when
# the API is unreachable (offline-safe).
MODEL_API_ROOT = "https://play.forum.ircam.fr/rave-vst-api/"

# ---------------------------------------------------------------------------
#  Shared Memory Header Structure (Handshake Protocol)
# ---------------------------------------------------------------------------

class SharedMemoryHeader(ctypes.Structure):
    """Header structure that Python creates and C++ reads.

    Version 3 adds method-aware metadata (channels_in/out, ratios, latent size
    and the active method name) so C++ can set up dynamic inlets/outlets, plus
    the per-inlet MC `channel_map` for mc.mab~ (Phase 5).
    Field order must match the C++ `SharedMemoryHeader` exactly.
    """
    _fields_ = [
        ("magic", ctypes.c_uint32),           # Validation signature 'MABT'
        ("version", ctypes.c_uint32),         # Header version (3)
        ("block_size", ctypes.c_uint32),      # Samples per audio block
        ("num_channels", ctypes.c_uint32),    # Legacy channel count
        ("channels_in", ctypes.c_uint32),     # Method input channels (decode/prior: latent)
        ("channels_out", ctypes.c_uint32),    # Method output channels (encode: latent)
        ("latent_size", ctypes.c_uint32),     # Latent dimension of the active method
        ("input_ratio", ctypes.c_uint32),     # Method input ratio (e.g. RAVE decode: 2048)
        ("output_ratio", ctypes.c_uint32),    # Method output ratio (e.g. RAVE decode: 1)
        ("method", ctypes.c_char * 52),       # Active method name: forward/encode/decode/prior
        ("method_id", ctypes.c_uint32),       # Stable hash of method for atomic C++ compare
        ("input_offset", ctypes.c_uint32),    # Byte offset to input buffer 0
        ("output_offset", ctypes.c_uint32),   # Byte offset to output buffer 0
        ("control_offset", ctypes.c_uint32),  # Byte offset to control ring buffer
        ("input_buffer_index", ctypes.c_uint32),   # A1: C++ fill index (0/1)
        ("output_buffer_index", ctypes.c_uint32),  # A1: C++ drain index (0/1)
        ("channel_map", ctypes.c_uint32 * 16),     # Phase 5: per-inlet channel counts (mc.mab~)
        ("is_input_ready", ctypes.c_long),    # atomic flag (volatile) - must match C++ long
        ("is_output_ready", ctypes.c_long),   # atomic flag (volatile) - must match C++ long
        ("is_python_ready", ctypes.c_long),   # atomic flag (volatile) - must match C++ long
        ("shutdown_flag", ctypes.c_long),     # atomic flag (volatile) - must match C++ long
    ]

# Control ring buffer constants (must match C++)
CONTROL_RING_SIZE = 256
CONTROL_MSG_SIZE = 256

class ControlRingBuffer(ctypes.Structure):
    """Lock-free SPSC ring buffer for control messages."""
    _fields_ = [
        ("head", ctypes.c_long),  # Written by C++ (producer)
        ("tail", ctypes.c_long),  # Written by Python (consumer)
        ("messages", ctypes.c_char * (CONTROL_RING_SIZE * CONTROL_MSG_SIZE)),
    ]


def _method_id(name: str) -> int:
    """Stable 32-bit hash for method names (matches C++ side)."""
    h = 0
    for c in name.encode("utf-8"):
        h = (h * 31 + c) & 0xFFFFFFFF
    return h


# ---------------------------------------------------------------------------
#  Shared Memory Management (Handshake Protocol)
# ---------------------------------------------------------------------------

class SharedMemoryManager:
    """
    Manages shared memory creation and handshake with C++.
    
    Protocol:
    1. Python creates shared memory with header
    2. Python signals ready event
    3. C++ opens the shared memory and reads header
    4. Both sides communicate via atomic flags in the header
    """
    
    def __init__(self, shm_name: str, ready_event_name: str,
                 block_size: int, channels_in: int, channels_out: int,
                 input_ready_event_name: str = "", n_batches: int = 1):
        """buffers are sized for the MAXIMUM channel counts across all methods,
        so a method switch never needs a shared-memory remap.

        Phase 6 (mcs.mab~): `n_batches` > 1 sizes the buffers batch-major
        [n_batches x channels x block_size]; the views returned by
        get_numpy_input/get_numpy_output are then 3-D (n_batches, channels,
        block_size) so the worker can feed all batches through the model in a
        single forward pass."""
        self.shm_name = shm_name
        self.ready_event_name = ready_event_name
        self.input_ready_event_name = input_ready_event_name or f"{shm_name}_InputReady"
        self.block_size = block_size
        self.channels_in = channels_in
        self.channels_out = channels_out
        self.n_batches = max(1, int(n_batches))
        
        # Calculate buffer sizes
        # A1: allocate two input and two output buffers for overlapped I/O.
        self.header_size = ctypes.sizeof(SharedMemoryHeader)
        self.control_size = ctypes.sizeof(ControlRingBuffer)
        self.input_size = block_size * channels_in * self.n_batches * 4  # float32 = 4 bytes, one buffer
        self.output_size = block_size * channels_out * self.n_batches * 4
        self.total_size = (self.header_size + self.control_size
                           + 2 * self.input_size + 2 * self.output_size)

        # Offsets
        self.control_offset = self.header_size
        self.input_offset = self.header_size + self.control_size
        self.output_offset = self.header_size + self.control_size + 2 * self.input_size
        
        # Handles
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

        # Korrekte 64-bit-Signaturen für die WinAPI-Aufrufe: Ohne argtypes
        # marshallt ctypes Integer als 32-bit (c_int), wodurch 64-bit-Handles
        # (z.B. INVALID_HANDLE_VALUE = (HANDLE)-1) abgeschnitten werden und
        # CreateFileMappingW/MapViewOfFile/SetEvent scheitern.
        self.kernel32.CreateFileMappingW.argtypes = [
            ctypes.c_void_p,   # hFile (INVALID_HANDLE_VALUE = (HANDLE)-1)
            ctypes.c_void_p,   # lpFileMappingAttributes
            ctypes.c_ulong,    # flProtect
            ctypes.c_ulong,    # dwMaximumSizeHigh
            ctypes.c_ulong,    # dwMaximumSizeLow
            ctypes.c_wchar_p,  # lpName
        ]
        self.kernel32.CreateFileMappingW.restype = ctypes.c_void_p
        self.kernel32.MapViewOfFile.argtypes = [
            ctypes.c_void_p,   # hFileMappingObject
            ctypes.c_ulong,    # dwDesiredAccess
            ctypes.c_ulong,    # dwFileOffsetHigh
            ctypes.c_ulong,    # dwFileOffsetLow
            ctypes.c_size_t,   # dwNumberOfBytesToMap (SIZE_T = 64-bit)
        ]
        self.kernel32.MapViewOfFile.restype = ctypes.c_void_p
        self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel32.CloseHandle.restype = ctypes.c_void_p
        self.kernel32.CreateEventW.argtypes = [
            ctypes.c_void_p,   # lpEventAttributes
            ctypes.c_ulong,    # bManualReset
            ctypes.c_ulong,    # bInitialState
            ctypes.c_wchar_p,  # lpName
        ]
        self.kernel32.CreateEventW.restype = ctypes.c_void_p
        self.kernel32.SetEvent.argtypes = [ctypes.c_void_p]
        self.kernel32.SetEvent.restype = ctypes.c_ulong
        self.kernel32.WaitForSingleObject.argtypes = [
            ctypes.c_void_p,   # hHandle
            ctypes.c_ulong,    # dwMilliseconds
        ]
        self.kernel32.WaitForSingleObject.restype = ctypes.c_ulong

        self._h_map = None
        self._p_header = None
        self._p_input = None
        self._p_output = None
        self._p_control = None
        self._h_ready_event = None
        self._h_input_ready_event = None

    def create(self) -> bool:
        """Create shared memory and initialize header."""
        # Create file mapping
        self._h_map = self.kernel32.CreateFileMappingW(
            ctypes.c_void_p(-1),  # INVALID_HANDLE_VALUE (64-bit) - Pagefile-Backing
            None,
            PAGE_READWRITE,
            0,
            self.total_size,
            self.shm_name
        )
        
        if not self._h_map:
            print(f"[inference_worker] Failed to create shared memory: {ctypes.WinError(ctypes.get_last_error())}")
            return False
        
        # Map view
        p_base = self.kernel32.MapViewOfFile(
            self._h_map,
            FILE_MAP_ALL_ACCESS,
            0,
            0,
            self.total_size
        )
        
        if not p_base:
            print(f"[inference_worker] Failed to map view: {ctypes.WinError(ctypes.get_last_error())}")
            self.kernel32.CloseHandle(self._h_map)
            return False
        
        # Cast to header structure
        self._p_header = SharedMemoryHeader.from_address(p_base)
        
        # Initialize header
        self._p_header.magic = MAGIC_NUMBER
        self._p_header.version = 3
        self._p_header.block_size = self.block_size
        self._p_header.num_channels = self.channels_out
        self._p_header.channels_in = self.channels_in
        self._p_header.channels_out = self.channels_out
        self._p_header.latent_size = 0
        self._p_header.input_ratio = 1
        self._p_header.output_ratio = 1
        self._p_header.method = b"forward"
        self._p_header.method_id = _method_id("forward")
        self._p_header.input_offset = self.input_offset
        self._p_header.output_offset = self.output_offset
        self._p_header.control_offset = self.control_offset
        self._p_header.input_buffer_index = 0
        self._p_header.output_buffer_index = 0
        self._p_header.is_input_ready = False
        self._p_header.is_output_ready = False
        self._p_header.is_python_ready = False
        
        # Get pointers to input/output buffers
        self._p_input = ctypes.cast(
            p_base + self.input_offset,
            ctypes.POINTER(ctypes.c_float)
        )
        self._p_output = ctypes.cast(
            p_base + self.output_offset,
            ctypes.POINTER(ctypes.c_float)
        )
        
        # Get pointer to control ring buffer
        self._p_control = ControlRingBuffer.from_address(p_base + self.control_offset)
        self._p_control.head = 0
        self._p_control.tail = 0

        # A4: input-ready event lets C++ wake us immediately instead of polling.
        self._h_input_ready_event = self.kernel32.CreateEventW(
            None,   # default security
            False,  # auto-reset
            False,  # not signaled initially
            self.input_ready_event_name
        )
        if not self._h_input_ready_event:
            print(f"[inference_worker] Failed to create input-ready event: {ctypes.WinError(ctypes.get_last_error())}")
            # non-fatal: fall back to sleep polling

        return True
    
    def apply_method(self, method: str, method_params: dict):
        """Publish the active method layout to the header (read by C++)."""
        if not method_params or method not in method_params:
            return
        ci, in_ratio, co, out_ratio = method_params[method]
        self._p_header.method = method.encode('utf-8')[:60]
        self._p_header.method_id = _method_id(method)
        self._p_header.channels_in = ci
        self._p_header.channels_out = co
        self._p_header.input_ratio = in_ratio
        self._p_header.output_ratio = out_ratio
        # latent side depends on the method:
        self._p_header.latent_size = ci if method in ("decode", "prior") \
            else (co if method == "encode" else 0)
    
    def signal_ready(self) -> bool:
        """Signal to C++ that Python is ready."""
        # Create or open the ready event
        self._h_ready_event = self.kernel32.CreateEventW(
            None,  # default security
            True,  # manual reset
            False, # not signaled initially
            self.ready_event_name
        )
        
        if not self._h_ready_event:
            print(f"[inference_worker] Failed to create ready event: {ctypes.WinError(ctypes.get_last_error())}")
            return False
        
        # Set the event to signal C++ that we're ready
        if not self.kernel32.SetEvent(self._h_ready_event):
            print(f"[inference_worker] Failed to set ready event: {ctypes.WinError(ctypes.get_last_error())}")
            return False
        
        # Mark Python as ready in the header
        self._p_header.is_python_ready = True
        
        return True
    
    def get_numpy_input(self, index: int = 0, channels: int = 0) -> np.ndarray:
        """Get NumPy view of input buffer `index` (zero-copy), sliced to `channels`.

        mcs.mab~ (Phase 6, n_batches > 1): batch-major view
        `(n_batches, channels_in, block_size)`; mono/mc.mab~: 2-D
        `(channels_in, block_size)`.
        """
        if channels <= 0:
            channels = self.channels_in
        base = ctypes.addressof(self._p_input.contents) + index * self.input_size
        total = self.block_size * self.channels_in * self.n_batches
        arr = np.frombuffer(
            (ctypes.c_float * total).from_address(base),
            dtype=np.float32
        )
        if self.n_batches > 1:
            return arr.reshape(self.n_batches, self.channels_in,
                               self.block_size)[:, :channels]
        return arr.reshape(self.channels_in, self.block_size)[:channels]

    def get_numpy_output(self, index: int = 0, channels: int = 0) -> np.ndarray:
        """Get NumPy view of output buffer `index` (zero-copy), sliced to `channels`.

        mcs.mab~ (Phase 6, n_batches > 1): batch-major view
        `(n_batches, channels_out, block_size)`; mono/mc.mab~: 2-D
        `(channels_out, block_size)`.
        """
        if channels <= 0:
            channels = self.channels_out
        base = ctypes.addressof(self._p_output.contents) + index * self.output_size
        total = self.block_size * self.channels_out * self.n_batches
        arr = np.frombuffer(
            (ctypes.c_float * total).from_address(base),
            dtype=np.float32
        )
        if self.n_batches > 1:
            return arr.reshape(self.n_batches, self.channels_out,
                               self.block_size)[:, :channels]
        return arr.reshape(self.channels_out, self.block_size)[:channels]

    def read_channel_map(self) -> list:
        """Per-inlet channel counts published by C++ (mc.mab~, Phase 5).

        Returns the list of non-zero entries: [channels_of_inlet_0, ...].
        Empty in mab~ (mono) mode where C++ never writes channel_map.
        """
        out = []
        for i in range(16):
            v = int(self._p_header.channel_map[i])
            if v <= 0:
                continue
            out.append(v)
        return out

    def get_total_input_channels(self) -> int:
        """Total connected MC channels = sum(channel_map).

        Falls back to header->channels_in when C++ has not published a map yet
        (mono mode, or before the first dsp64 call).
        """
        total = 0
        for i in range(16):
            v = int(self._p_header.channel_map[i])
            if v > 0:
                total += v
        if total <= 0:
            total = int(self._p_header.channels_in)
        return total
    
    def cleanup(self):
        """Clean up handles."""
        if self._h_input_ready_event:
            self.kernel32.CloseHandle(self._h_input_ready_event)
        if self._h_ready_event:
            self.kernel32.CloseHandle(self._h_ready_event)
        if self._p_header:
            # Unmap is handled when process exits
            pass
        if self._h_map:
            self.kernel32.CloseHandle(self._h_map)


# ---------------------------------------------------------------------------
#  Lock-Free Ring Buffer (Control Messages)
# ---------------------------------------------------------------------------

class LockFreeRingBuffer:
    """
    Lock-free SPSC ring buffer for control messages.
    Uses atomic head/tail indices for lock-free operation.
    """
    
    def __init__(self, max_items: int = 1024):
        self._max_items = max_items
        self._head = 0
        self._tail = 0
        self._msgs = [0] * max_items
    
    def enqueue(self, msg_ptr: int) -> bool:
        """Enqueue a message (called by C++ side)."""
        # Check if queue is full
        if (self._head - self._tail) % self._max_items == self._max_items - 1:
            return False
        
        idx = self._head % self._max_items
        self._msgs[idx] = msg_ptr
        # Memory barrier
        self._head += 1
        return True
    
    def dequeue(self) -> Optional[int]:
        """Dequeue a message (called by Python side)."""
        if self._head == self._tail:
            return None
        
        idx = self._tail % self._max_items
        msg_ptr = self._msgs[idx]
        self._tail += 1
        return msg_ptr


# ---------------------------------------------------------------------------
#  P7 (Vorbereitung): Zukünftige Buffer~-API (nn_tilde-Parität)
# ---------------------------------------------------------------------------
#  Erledigt in Phase 5 zusammen mit dem nativen Max-SDK buffer_reference in
#  C++ (buffer_manager.h). Geplante Control-Messages an den Worker:
#
#    track_buffers <0/1>              Buffer-Tracking ein/aus (Default: 0)
#    set <attr> <buffer~name>         Verlinkt Modell-Buffer-Attribut mit
#                                     einem Max-Buffer~
#    notify <key> <buffer~name> <len> <sr> <channels>
#                                     Buffer-Update an Max melden
#    print <key>                      Download-/Buffer-Progress (intern)
#
#  Datenfluss: C++ (buffer_manager.h) -> ControlRingBuffer -> dieser Loop;
#  die Buffer-Daten selbst werden über den Shared-Memory-Bereich bereit-
#  gestellt (max. 16 Buffer-Referenzen à MAX_BLOCK_SIZE Frames). Tensor-
#  Attribute (Typ 4) akzeptieren statt buffer~ einen Max-`array`-Namen.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
#  Model handling utilities
# ---------------------------------------------------------------------------

def resolve_model_path(path: str, worker_dir: str = None) -> str:
    """Resolve a model name/path to an absolute file path.

    Bare names (no directory separator, no existing file) are searched in the
    worker's package directories so `mab~ musicnet` / `mab.info set musicnet`
    work without an absolute path:

      <package>/support/models/
      <package>/support/
      <package>/models/
      <package>/ts_models/
      <package>/models/ts/                    (nn_tilde layout)

    Returns the input unchanged if nothing is found so the caller can produce
    the original "file does not exist" error.
    """
    if not path:
        return path
    if os.path.isfile(path):
        return os.path.abspath(path)

    has_sep = any(s in path for s in ("\\", "/"))
    if has_sep:
        return path  # path-like, keep as-is (error surfaces at load)

    base = os.path.abspath(worker_dir) if worker_dir else \
        os.path.dirname(os.path.abspath(__file__))
    pkg = os.path.abspath(os.path.join(base, ".."))
    names = [path]
    if not os.path.splitext(path)[1]:
        names.append(path + ".ts")
    for n in names:
        for d in (os.path.join(base, "models"), base,
                  os.path.join(pkg, "models"), os.path.join(pkg, "ts_models"),
                  os.path.join(pkg, "models", "ts")):
            c = os.path.join(d, n)
            if os.path.isfile(c):
                return os.path.abspath(c)
    return path


def load_model(model_path: str, use_gpu: bool):
    """Load a TorchScript model, moving it to CPU or CUDA as requested."""
    if use_gpu and torch.cuda.is_available():
        device = torch.device('cuda')
    else:
        device = torch.device('cpu')
    
    # torch.jit.load returns a scripted module ready for inference
    mod = torch.jit.load(resolve_model_path(model_path), map_location=device)
    mod.eval()  # inference mode
    return mod, device


def extract_block_size(model) -> int:
    """
    Extract the expected block size from the model's input shape.
    
    TorchScript models may have input shapes like:
    - (1, num_channels, block_size) - typical for audio models
    - (num_channels, block_size) - 2D input
    
    Returns the block_size if found, or 0 if it cannot be determined.
    """
    try:
        # Try to get input shapes from the model's graph
        if hasattr(model, 'graph'):
            for node in model.graph.nodes():
                for inp in node.inputs():
                    # Check if this input has a shape
                    if hasattr(inp, 'type') and hasattr(inp.type(), 'sizes'):
                        sizes = inp.type().sizes()
                        if sizes and len(sizes) >= 2:
                            # Last dimension is typically block_size
                            block_size = sizes[-1]
                            if isinstance(block_size, int) and block_size > 0:
                                return block_size
    except Exception:
        pass
    
    # Try alternative method: check model's forward method signature
    try:
        if hasattr(model, 'forward'):
            # Try to get example input shapes
            if hasattr(model, 'example_inputs'):
                for inp in model.example_inputs:
                    if hasattr(inp, 'shape') and len(inp.shape) >= 2:
                        return inp.shape[-1]
    except Exception:
        pass
    
    # Try to infer from the model's parameters
    try:
        for param in model.parameters():
            if hasattr(param, 'shape') and len(param.shape) >= 2:
                # Some models have parameters that indicate block size
                # This is a heuristic and may not work for all models
                pass
    except Exception:
        pass
    
    return 0  # Could not determine block size


def get_method_params(model) -> dict:
    """Extract {method}_params for every method a TorchScript model exposes.

    Returns a dict mapping method name -> (channels_in, input_ratio,
    channels_out, output_ratio). Falls back to heuristic detection for the
    standard RAVE/AFTER methods.
    """
    methods = []
    try:
        if hasattr(model, '_c'):
            methods = list(model._c.get_methods())
    except Exception:
        pass
    if not methods:
        methods = [m for m in ("forward", "encode", "decode", "prior")
                   if hasattr(model, m)]

    params = {}
    for m in methods:
        try:
            p = getattr(model, m + "_params")
            if hasattr(p, "detach"):
                p = p.detach()
            p = p.tolist() if hasattr(p, "tolist") else list(p)
            plist = [int(v) for v in p[:4]]
            if len(plist) >= 4:
                params[m] = tuple(plist)
        except Exception:
            continue
    return params


# ---------------------------------------------------------------------------
#  Model inspection (--query mode for mab.info)
# ---------------------------------------------------------------------------

def detect_model_type(model) -> str:
    """Heuristic model-type detection (RAVE / AFTER / MusicNet / ...)."""
    name = ""
    try:
        name = str(model._c._type().name())
    except Exception:
        pass
    if not name:
        try:
            name = str(model)
        except Exception:
            name = ""
    up = name.upper()
    if "RAVE" in up:
        return "RAVE"
    if "AFTER" in up:
        return "AFTER"
    if "MUSICNET" in up or "MUSIC-NET" in up:
        return "MusicNet"
    if name:
        return "TorchScript"
    return "unknown"


def get_method_labels(model, method: str):
    """Return ({method}_input_labels, {method}_output_labels) or (None, None)."""
    def to_list(attr):
        try:
            v = getattr(model, attr, None)
            if v is None:
                return None
            return list(v)
        except Exception:
            return None
    return to_list(method + "_input_labels"), to_list(method + "_output_labels")


def get_method_attributes(model, method_params: dict) -> dict:
    """Extra values in {method}_params beyond (ci, in_ratio, co, out_ratio).

    RAVE/AFTER models often pack additional tunables (sample rate, latent
    stride, ...) into the parameter vector. These are reported as the
    "available attributes" for each method.
    """
    extras = {}
    for m in method_params:
        try:
            p = getattr(model, m + "_params")
            if hasattr(p, "detach"):
                p = p.detach()
            p = p.tolist() if hasattr(p, "tolist") else list(p)
            plist = [float(v) for v in p]
            if len(plist) > 4:
                extras[m] = [v for v in plist[4:] if v == v]  # drop NaN
        except Exception:
            continue
    return extras


# Attribute names commonly exposed by RAVE/AFTER-style models. Values are read
# from the module (bounded to a few dozen scalars) and reported by mab.info.
KNOWN_ATTRIBUTE_PATTERNS = (
    "sr", "sample_rate", "latent_size", "latent_dim", "channels", "channels_in",
    "channels_out", "n_fft", "window_size", "hop", "latent_mean", "latent_pca",
)


def detect_model_attributes(model) -> dict:
    """Scan the module for small, readable attributes (bounded values only)."""
    attrs = {}
    for n in dir(model):
        ln = n.lower()
        if not any(k in ln for k in KNOWN_ATTRIBUTE_PATTERNS):
            continue
        try:
            v = getattr(model, n)
            if isinstance(v, torch.Tensor):
                if v.numel() > 32 or v.numel() == 0:
                    continue
                v = v.tolist()
            if isinstance(v, (list, tuple)):
                if len(v) > 32:
                    continue
                v = [round(float(x), 4) if isinstance(x, (int, float)) else str(x)
                     for x in v]
            if isinstance(v, (int, float, bool, str)):
                if isinstance(v, float):
                    v = round(v, 6)
                attrs[n] = v
        except Exception:
            continue
    return attrs


def collect_model_info(model, model_path: str) -> dict:
    """Build the metadata dict for a loaded model (no file I/O beyond size)."""
    method_params = get_method_params(model)
    block_size, max_in, max_out = compute_layout(method_params, 0)
    methods = sorted(method_params.keys())
    attributes = detect_model_attributes(model)
    method_attrs = get_method_attributes(model, method_params)
    return {
        "model_path": model_path,
        "model_type": detect_model_type(model),
        "model_size_mb": round(os.path.getsize(model_path) / (1024.0 * 1024.0), 2),
        "load_time_ms": 0.0,
        "methods": methods,
        "params": {m: [int(v) for v in method_params[m]] for m in methods},
        "attributes": attributes,
        "method_attributes": method_attrs,
        "labels": {m: get_method_labels(model, m) for m in methods},
        "layout": {"block_size": block_size,
                   "channels_in": max_in,
                   "channels_out": max_out},
    }


def print_info_block(info: dict):
    """Print the MABJSON line + MAB_INFO block for C++ parsing."""
    import json

    print("MABJSON " + json.dumps(info))
    print("MAB_INFO_BEGIN")
    if info.get("error"):
        print("error: %s" % info["error"])
    else:
        lay = info["layout"]
        print("model_path: %s" % info["model_path"])
        print("model_type: %s" % info["model_type"])
        print("model_size_mb: %s" % info["model_size_mb"])
        print("load_time_ms: %s" % info["load_time_ms"])
        print("block_size: %d" % lay["block_size"])
        print("channels_in: %d" % lay["channels_in"])
        print("channels_out: %d" % lay["channels_out"])
        print("latent_size: %d" % max(lay["channels_in"], lay["channels_out"]))
        print("methods: " + "; ".join(info["methods"]))
        attr_parts = ["%s=%s" % (m, ",".join("%g" % v for v in vs))
                      for m, vs in info["method_attributes"].items()]
        attr_parts += ["%s=%s" % (n, v) for n, v in info["attributes"].items()]
        print("attributes: " + ("; ".join(attr_parts) if attr_parts else "-"))
        for m in info["methods"]:
            ci, in_ratio, co, out_ratio = info["params"][m]
            print("param %s: %d %d %d %d" % (m, ci, in_ratio, co, out_ratio))
    print("MAB_INFO_END")


def query_model(model_path: str):
    """Load a model, print a machine-readable info block to stdout, exit 0.

    Output format (parsed by mab.info):
      MABJSON <json-dict>        - one-line JSON for external tooling
      MAB_INFO_BEGIN             - line-oriented block that C++ parses
      key: value                 - model_path, model_type, block_size,
                                   channels_in/out, latent_size, methods,
                                   attributes, per-method "param <m>: ci in co out"
      MAB_INFO_END

    Prints the JSON with an "error" key and exits with 1 on failure.
    """
    import json

    t0 = time.time()
    resolved = resolve_model_path(model_path)
    info = {"error": "unknown failure", "model_path": resolved}
    try:
        model, device = load_model(model_path, False)
        info = collect_model_info(model, resolved)
        info["load_time_ms"] = round((time.time() - t0) * 1000.0, 1)
    except Exception as exc:
        msg = str(exc)
        if not os.path.isfile(resolved):
            base = os.path.dirname(os.path.abspath(__file__))
            pkg = os.path.abspath(os.path.join(base, ".."))
            msg = ("Model '%s' not found. Searched: %s (as given), %s\\models, "
                   "%s\\ts_models, %s\\models\\ts. Pass an absolute path or put "
                   "the .ts file into <package>\\models."
                   % (model_path, base, pkg, pkg, pkg))
        info = {"error": msg, "model_path": resolved}

    if "model" in locals():
        del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print_info_block(info)
    sys.exit(0 if not info.get("error") else 1)


def compute_layout(method_params: dict, requested_block_size: int):
    """Choose block size and channel maxima from all method layouts.

    block_size must hold any input/output ratio (latent frames are held at
    audio rate), so it is the max of the requested size and all ratios.
    Buffers are sized for the maximum channels_in/out over all methods so a
    method switch never requires a shared-memory remap.
    """
    block_size = max(int(requested_block_size), 1)
    max_in = 1
    max_out = 1
    for ci, in_ratio, co, out_ratio in method_params.values():
        block_size = max(block_size, int(in_ratio), int(out_ratio))
        max_in = max(max_in, int(ci))
        max_out = max(max_out, int(co))
    return block_size, max_in, max_out


class ConvStreamingContext:
    """Cross-block history buffer for convolutional RAVE models.

    RAVE models exported **without** ``--streaming`` use standard Conv1d with
    zero-padding instead of ``cached-conv`` registered buffers.  Feeding
    isolated blocks creates discontinuities at convolution boundaries that
    amplify through the decoder into **NaN / Inf / overloads** and crash Max's
    audio engine («Bug 1»).

    This class maintains sliding input-history buffers that are prepended
    before each inference call, providing the smooth cross-block context that
    convolution layers require.  It auto-detects whether the model uses
    convolutions at all; for simple feedforward models it is a transparent
    no-op.
    """

    _HISTORY_BLOCKS = 8

    def __init__(self, model, block_size):
        self._needs_streaming = self._has_conv_layers(model)
        self._block_size = block_size
        self._context_size = block_size * self._HISTORY_BLOCKS
        self._input_history = {}

    @staticmethod
    def _has_conv_layers(model):
        has_conv = False
        has_streaming_buffers = False
        for name, mod in model.named_modules():
            if hasattr(mod, 'weight') and mod.weight is not None:
                if mod.weight.ndim >= 3:
                    has_conv = True
            for p_name, p in mod.named_parameters(recurse=False):
                if p.ndim >= 3:
                    has_conv = True
            for b_name, _ in mod.named_buffers(recurse=False):
                lower = b_name.lower()
                if 'pad' in lower or 'cache' in lower:
                    has_streaming_buffers = True

        # Only activate streaming wrapper when the model has convolution
        # layers WITHOUT built-in cached-conv streaming buffers (Bug 1).
        return has_conv and not has_streaming_buffers

    @property
    def active(self):
        return self._needs_streaming

    def reset(self):
        self._input_history.clear()

    def prepend_history(self, method, ci, device, tensor):
        """Prepend input history to *tensor*.

        Returns ``(padded_tensor, save_context)`` where *save_context* is
        ``None`` when streaming is inactive (no-op), otherwise a tuple to be
        passed to :meth:`save_history` after inference.
        """
        if not self._needs_streaming:
            return tensor, None

        if method not in self._input_history:
            B = tensor.shape[0] if tensor.ndim == 3 else 1
            self._input_history[method] = torch.zeros(
                B, ci, self._context_size, device=device)

        hist = self._input_history[method]
        if hist.shape[0] < tensor.shape[0]:
            hist = hist.expand(tensor.shape[0], -1, -1)
        else:
            hist = hist[:tensor.shape[0]]

        padded = torch.cat([hist.to(device), tensor], dim=-1)
        return padded, (method, padded)

    def save_history(self, context):
        """Store the tail of the padded input for the next block."""
        if context is None:
            return
        method, padded = context
        cs = self._context_size
        self._input_history[method][:padded.shape[0]] = \
            padded[..., -cs:].detach().cpu()


def infer_method(model, device, method: str, method_params: dict,
                 input_block: np.ndarray,
                 streaming_context: Optional[ConvStreamingContext] = None,
                 safety_clip: bool = False
                 ) -> np.ndarray:
    """
    Run one audio block through the model using nn_tilde semantics.

    forward / encode : the full audio block is fed in (channels_in, block_size).
    decode / prior   : only the LAST sample of each channel is taken as the
                       latent frame (nn_tilde `select(-1,-1)` semantics); the
                       output is then held to block_size by repeating frames
                       `output_ratio` times.

    Phase 6 (mcs.mab~): a 3-D input block `(n_batches, channels_in,
    block_size)` runs all batches through the model in ONE batched forward
    pass (output `(n_batches, channels_out, block_size)`). A 2-D input block
    keeps the original single-batch behaviour (output `(channels_out,
    block_size)`), so existing callers stay unchanged.

    *streaming_context* (optional) provides cross-block input history for
    convolutional RAVE models that were exported without ``--streaming``,
    preventing convolution boundary artifacts (Bug 1).

    *safety_clip* (bool) applies hard clipping to ``[-1.0, 1.0]`` after
    NaN/Inf zeroing.  Required in the real-time Max loop to prevent buffer
    overflows; disabled by default so unit-tests see raw model output.
    """
    ci, in_ratio, co, out_ratio = method_params[method]
    block_size = input_block.shape[-1]
    batched = input_block.ndim == 3

    tensor = torch.from_numpy(np.ascontiguousarray(input_block)).to(device)

    save_ctx = None
    if streaming_context is not None:
        tensor, save_ctx = streaming_context.prepend_history(
            method, ci, device, tensor)

    with torch.no_grad():
        if method in ("decode", "prior"):
            if batched:
                z = tensor[..., -1].unsqueeze(-1)          # (B, ci, 1)
            else:
                z = tensor[:, -1].unsqueeze(0).unsqueeze(-1)  # (1, ci, 1)
            out = getattr(model, method)(z)
        else:
            if not batched:
                tensor = tensor.unsqueeze(0)  # (1, ci, block_size)
            out = getattr(model, method)(tensor)

    if streaming_context is not None:
        streaming_context.save_history(save_ctx)

    out = out.detach().cpu()
    if out.dim() == 2:
        out = out.unsqueeze(0)   # (B, co, frames)
    if out.dim() < 3:
        out = out.unsqueeze(-1)

    # Hold latent/audio frames: repeat each frame output_ratio times.
    # B4 fix: forward produces audio-rate output directly — no interleave needed.
    if method != "forward":
        out = out.repeat_interleave(out_ratio, dim=-1)

    # Trim output tail when history was prepended: the extra samples at the
    # beginning correspond to the history context; keep only the portion
    # belonging to the new input block.
    if save_ctx is not None:
        expected_new = max(1, int(block_size * out_ratio / in_ratio))
        if out.size(-1) >= expected_new:
            out = out[..., -expected_new:]

    # Pad or trim to exactly block_size samples
    if out.size(-1) < block_size:
        pad = torch.zeros(out.size(0), out.size(1), block_size - out.size(-1))
        out = torch.cat([out, pad], dim=-1)
    elif out.size(-1) > block_size:
        out = out[..., :block_size]

    # Pad channels if the model produced fewer than declared
    if out.size(1) < co:
        pad = torch.zeros(out.size(0), co - out.size(1), out.size(-1))
        out = torch.cat([out, pad], dim=1)

    # Safety guard (Bug 1): RAVE models can produce NaN/Inf through
    # convolution boundary artifacts.  Zero out non-finite values to prevent
    # Max's audio engine from crashing.
    if not torch.isfinite(out).all():
        out = torch.where(torch.isfinite(out), out, torch.zeros_like(out))

    # Optional hard clipping to [-1.0, 1.0] for real-time Max safety.
    if safety_clip:
        out = torch.clamp(out, -1.0, 1.0)

    if batched:
        return out[:, :co, :block_size].numpy().astype(np.float32)  # (B, co, bs)
    return out[0, :co, :block_size].numpy().astype(np.float32)      # (co, bs)


# ---------------------------------------------------------------------------
#  Message processing
# ---------------------------------------------------------------------------

def _coerce_value(raw, current=None):
    """nn_tilde-style type coercion for attribute values.

    When the model exposes the current value (TorchScript `_c.get_attribute`),
    its type decides bool/int/float/str so values survive intact. Without a
    known type, falls back to string-based coercion (bool -> int -> float ->
    str), matching nn_tilde's type-hash semantics.
    """
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip()
    low = s.lower()

    if isinstance(current, str):
        return str(raw)

    if current is not None and not isinstance(current, str):
        if isinstance(current, bool):
            return low in ("true", "1", "yes", "on", "t")
        if isinstance(current, int):
            try:
                return int(low)
            except ValueError:
                try:
                    return int(float(low))
                except ValueError:
                    return current
        if isinstance(current, float):
            try:
                return float(low)
            except ValueError:
                return current

    if low in ("true", "1", "yes", "on", "t"):
        return True
    if low in ("false", "0", "no", "off", "f"):
        return False
    try:
        return int(low)
    except ValueError:
        pass
    try:
        return float(low)
    except ValueError:
        pass
    return raw


def _read_model_attribute(model, name):
    """Read a model attribute (TorchScript or Python), bounded for output."""
    if model is None or not name:
        return None
    # Version-tolerante TorchScript-API: neuer _c.getattr, älterer
    # _c.get_attribute, dann Python-getattr.
    for fn in ("getattr", "get_attribute"):
        try:
            v = getattr(model._c, fn)(name)
            break
        except Exception:
            v = None
    else:
        try:
            v = getattr(model, name)
        except Exception:
            return None
    if isinstance(v, torch.Tensor):
        if v.numel() <= 32 and v.numel() > 0:
            return v.tolist()
        return "<tensor %s>" % (tuple(v.shape),)
    if callable(v):
        return "<method>"
    return v


def _apply_model_attribute(model, name, value):
    """Set a model attribute with type coercion (nn_tilde passthrough).

    Returns (ok, coerced_value_or_error). On success the coerced value is
    returned so it can be stored for later `get` / re-apply after reload.
    """
    if model is None or not name:
        return False, "no model"
    # Strictness: echte ScriptModule (z. B. .ts-Dateien) lehnen Namen ab, die
    # nicht deklariert sind - sonst entsteht ein stilles Python-Attribut, das
    # nach einem Reload verloren geht. Plain-Python-Objekte bleiben permissiv.
    if hasattr(model, "_c"):
        try:
            if model._c.hasattr(name) is False:
                return False, "attribute '%s' is not declared on the model" % name
        except Exception:
            pass
    current = None
    try:
        current = model._c.getattr(name)
    except Exception:
        try:
            current = model._c.get_attribute(name)
        except Exception:
            try:
                current = getattr(model, name)
            except Exception:
                current = None
    coerced = _coerce_value(value, current)
    # setattr zuerst (Python-Module + einfache ScriptModule), dann die
    # TorchScript-C-API (echte .ts-Modelle).
    try:
        setattr(model, name, coerced)
        return True, coerced
    except Exception:
        pass
    for fn in ("setattr", "set_attribute"):
        try:
            getattr(model._c, fn)(name, coerced)
            return True, coerced
        except Exception:
            continue
    return False, "attribute '%s' could not be set on the model" % name


def _reapply_attributes(model, runtime_attrs):
    """Re-apply all stored attributes after a model reload / device switch."""
    if model is None:
        return
    for name, value in list(runtime_attrs.attrs.items()):
        ok, result = _apply_model_attribute(model, name, value)
        if not ok:
            print(f"[inference_worker] re-apply {name}: {result}")


def _list_model_attributes(model, runtime_attrs):
    """Union of runtime-stored + model-declared attribute names (sorted).

    Declared attributes are discovered best-effort, da die TorchScript-C-API
    je nach Torch-Version unterschiedlich heißt (get_attributes() existiert in
    neueren Builds nicht mehr, _c.hasattr/getattr schon). Kandidaten: bekannte
    Muster (RAVE/AFTER), im Module-Code referenzierte self.<name> sowie
    vorhandene Attribute; jeder Kandidat wird per hasattr verifiziert.
    """
    names = set()
    try:
        names.update(runtime_attrs.attrs.keys())
    except Exception:
        pass
    if model is not None:
        candidates = set()
        try:
            candidates.update(str(n) for n in model._c.get_attributes())
        except Exception:
            pass
        try:
            candidates.update(str(k) for k in detect_model_attributes(model).keys())
        except Exception:
            pass
        try:
            code_src = model.code if hasattr(model, "code") else ""
            import re
            candidates.update(re.findall(r"\bself\.(\w+)", code_src))
        except Exception:
            pass
        for n in candidates:
            if n.startswith("_"):
                continue
            try:
                if model._c.hasattr(n):
                    names.add(n)
            except Exception:
                try:
                    if hasattr(model, n):
                        names.add(n)
                except Exception:
                    pass
    return sorted(names)


class RuntimeAttributes:
    """Container for mutable model attributes (nn_tilde `register_attribute`)."""

    def __init__(self):
        self.attrs = {}

    def set(self, name: str, value, model=None):
        """Set an attribute: applies it to the model (if present), coerced by
        the model's registered type, and stores it for `get`/re-apply."""
        ok, result = _apply_model_attribute(model, name, value)
        if ok:
            self.attrs[name] = result
            return "applied %s = %r" % (name, result)
        coerced = _coerce_value(value)
        self.attrs[name] = coerced
        return "stored %s = %r (%s)" % (name, coerced, result)

    def get(self, name: str, model=None):
        """Get an attribute value (runtime cache first, then the model)."""
        if name in self.attrs:
            return self.attrs[name]
        return _read_model_attribute(model, name)


def _models_dir(worker_dir=None):
    """Directory used for model download / delete (the package `models` dir)."""
    base = os.path.abspath(worker_dir) if worker_dir else \
        os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(base, "..", "models"))


def list_local_models(worker_dir=None):
    """Map <filename> -> abs path of every .ts found in the known model dirs."""
    base = os.path.abspath(worker_dir) if worker_dir else \
        os.path.dirname(os.path.abspath(__file__))
    pkg = os.path.abspath(os.path.join(base, ".."))
    dirs = [os.path.join(base, "models"), base,
            os.path.join(pkg, "models"), os.path.join(pkg, "ts_models"),
            os.path.join(pkg, "models", "ts")]
    found = {}
    for d in dirs:
        if not os.path.isdir(d):
            continue
        try:
            for fn in sorted(os.listdir(d)):
                if fn.lower().endswith(".ts"):
                    found.setdefault(fn, os.path.join(d, fn))
        except Exception:
            continue
    return found


def _remote_available_models():
    """Best-effort list of downloadable model cards from the IRCAM API."""
    import json
    url = MODEL_API_ROOT + "available_models"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = r.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)
    try:
        lst = json.loads(data)
        if isinstance(lst, dict):
            lst = lst.get("models") or list(lst.keys())
        if isinstance(lst, list):
            return [str(x) for x in lst if str(x).strip()], None
    except Exception:
        pass
    lines = [ln.strip() for ln in data.splitlines() if ln.strip()]
    return (lines or ["<unparsed response>"]), None


def download_model(card: str, name=None, worker_dir=None):
    """Download a model card from the IRCAM API into the package models dir.

    Returns (ok, message). Never raises on network failure.
    """
    if not card:
        return False, "download requires a model card"
    target_dir = _models_dir(worker_dir)
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as exc:
        return False, "cannot create %s: %s" % (target_dir, exc)
    fname = name or card
    if not fname.lower().endswith(".ts"):
        fname += ".ts"
    out = os.path.join(target_dir, fname)
    url = MODEL_API_ROOT + "download_model?model=" + urllib.parse.quote(card)
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
        with open(out, "wb") as f:
            f.write(data)
        return True, out
    except Exception as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)


def delete_model(card: str, worker_dir=None):
    """Delete a local .ts model (only within the known model directories).

    Returns (ok, message).
    """
    if not card:
        return False, "delete requires a model name"
    found = list_local_models(worker_dir)
    for fn, path in found.items():
        base = os.path.splitext(fn)[0]
        if fn == card or fn == card + ".ts" or base == card:
            try:
                os.remove(path)
                return True, path
            except Exception as exc:
                return False, "%s: %s" % (type(exc).__name__, exc)
    return False, "not found (looking for '%s' among local .ts models)" % card


def dump_model_info(model_path: str, method: str, device, attrs: dict,
                    model=None, method_params=None):
    """Print model information to stdout (captured by Max)."""
    print("[inference_worker] Model dump:")
    print(f"  Model path   : {model_path}")
    print(f"  Method       : {method}")
    print(f"  Device       : {device}")
    print(f"  Attributes   : {attrs}")
    if method_params:
        print("  Methods      : " + "; ".join(sorted(method_params)))
        for m, p in sorted(method_params.items()):
            print(f"  Param {m}    : {p}")
    if model is not None:
        print(f"  Model type   : {detect_model_type(model)}")
        attr_names = _list_model_attributes(model, RuntimeAttributes())
        if attr_names:
            print("  Model attrs  : " + "; ".join(
                "%s=%r" % (n, _read_model_attribute(model, n)) for n in attr_names))
        else:
            print("  Model attrs  : -")
    
    # Try to get model input/output shapes
    try:
        if model is not None and hasattr(model, 'graph'):
            print(f"  Graph inputs : {model.graph.inputs()}")
            print(f"  Graph outputs: {model.graph.outputs()}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
#  Main worker
# ---------------------------------------------------------------------------

def _limit_inference_threads(cores):
    """Begrenzt die PyTorch-Inference-Threads (NUR im CPU-Modus relevant).

    Setzt die OpenMP/MKL/OpenBLAS-Umgebungsvariablen und ruft
    torch.set_num_threads auf. Die Backends lesen die Variablen lazy beim
    ersten Parallel-Block, daher VOR dem ersten Modell-Load aufrufen.
    Im GPU-Modus inaktiv (AGENTS.md Regel 8, WORKSPACE_AGENT_PROMPT §3.8):
    CUDA-Inferenz nutzt keine OpenMP/MKL-Threads.
    """
    cores = int(cores or 1)
    if cores < 1:
        cores = 1
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[var] = str(cores)
    try:
        torch.set_num_threads(cores)
    except Exception:
        pass
    print(f"[inference_worker] Inference threads limited to {cores} (CPU mode)")
    return cores


def _init_xrun_prevention():
    """FR1: ASIO XRun-Prävention durch Timer-Resolution + Thread-Priorität.

    1) ``timeBeginPeriod(1)`` setzt die Windows-Timer-Resolution auf 1 ms
       (Standard: ~15.6 ms).  Ohne diesen Call schläft ``WaitForSingleObject``
       mit 10 ms-Timeout real ~16 ms.  Mit 1 ms-Resolution wacht der Python-
       Worker deutlich schneller auf und kann Output-Blöcke pünktlicher liefern.

    2) ``SetThreadPriority(THREAD_PRIORITY_LOWEST)`` stellt sicher, dass der
       Audio-Thread (Max/ASIO, läuft in einem HIGH/RT-Kontext) den Python-
       Haupt-Thread auch innerhalb des ``BELOW_NORMAL_PRIORITY_CLASS``-Prozesses
       jederzeit präemptieren kann.
    """
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    try:
        kernel32.timeBeginPeriod.restype = ctypes.c_uint
        kernel32.timeBeginPeriod.argtypes = [ctypes.c_uint]
        kernel32.timeBeginPeriod(1)
        kernel32.SetThreadPriority.restype = ctypes.c_int
        kernel32.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
        kernel32.GetCurrentThread.restype = ctypes.c_void_p
        kernel32.SetThreadPriority(kernel32.GetCurrentThread(), -2)
    except Exception:
        pass


def _load_and_configure(model_path: str, use_gpu: bool, active_method: str,
                        method_params: dict, attrs: RuntimeAttributes, shm,
                        streaming_ctx: Optional[ConvStreamingContext] = None):
    """Load a model, re-validate the method, publish the layout, re-apply
    the runtime attributes, and (re-)create the streaming context.

    Used by reload / load / gpu switch.
    """
    model, device = load_model(model_path, use_gpu)
    new_params = get_method_params(model)
    if new_params and active_method not in new_params:
        active_method = "forward" if "forward" in new_params \
            else next(iter(new_params), active_method)
    if shm is not None:
        shm.apply_method(active_method, new_params)
    _reapply_attributes(model, attrs)

    block_size, _, _ = compute_layout(new_params, 0)
    streaming_ctx = ConvStreamingContext(model, max(block_size, 64))
    if streaming_ctx.active:
        print(f"[inference_worker] ConvStreamingContext active "
              f"(history={streaming_ctx._context_size} samples)")

    return model, device, new_params, active_method, streaming_ctx


def main():
    parser = argparse.ArgumentParser(
        description="Python backend for MaxMSP mab~ / mc.mab~"
    )
    parser.add_argument("model", nargs='?', default="", help="Path to the TorchScript model (.ts), or empty for lazy loading")
    parser.add_argument("method", nargs='?', default="forward", help="Default inference method (e.g. forward)")
    parser.add_argument("bufsize", type=int, nargs='?', default=512, help="Audio block size in samples")
    parser.add_argument("gpu", type=int, nargs='?', default=0, help="0 = CPU only, 1 = GPU if available")
    parser.add_argument("n_batches", type=int, nargs='?', default=1,
                        help="Number of parallel batch inlets/outlets (mcs.mab~, Phase 6; 1 = mab~/mc.mab~)")
    parser.add_argument("shm_name", nargs='?', default="", help="Shared memory name (from C++)")
    parser.add_argument("instance_id", type=int, nargs='?', default=0, help="Process ID for event naming")
    parser.add_argument("num_channels", type=int, nargs='?', default=1, help="Number of audio channels (1 for mab~, up to 16 for mc.mab~)")
    parser.add_argument("cores", type=int, nargs='?', default=2,
                        help="PyTorch inference threads (default 2: balanced "
                             "load without the all-core thread spread that "
                             "causes ASIO XRuns)")
    parser.add_argument("--query", action="store_true",
                        help="Inspection mode for mab.info: load the model, print an info block on stdout and exit")
    # P11: Standalone-Befehle für mab.info (nn_tilde-Parität). Starten einen
    # kurzen Worker-Lauf ohne Shared Memory / Modell, schreiben das Ergebnis
    # als stdout-Zeilen (werden von mab_info.cpp auf Outlet 1 ausgegeben).
    parser.add_argument("--download", nargs='+', metavar="CARD [NAME]",
                        help="Download a model card from the IRCAM API, print the result and exit")
    parser.add_argument("--delete", metavar="CARD",
                        help="Delete a local .ts model, print the result and exit")
    parser.add_argument("--list", action="store_true",
                        help="Print local + remote (IRCAM API) available models and exit")
    args = parser.parse_args()

    # P11: Standalone-Befehle VOR der Inferenz/Query ausführen und beenden.
    if args.download:
        card = args.download[0]
        name = args.download[1] if len(args.download) > 1 else None
        ok, msg = download_model(card, name)
        print(f"download: {msg}")
        sys.exit(0 if ok else 1)
    if args.delete:
        ok, msg = delete_model(args.delete)
        print(f"delete: {msg}")
        sys.exit(0 if ok else 1)
    if args.list:
        local = list_local_models()
        print("Local models:")
        if local:
            for fn, path in sorted(local.items()):
                print(f"  {fn}  ({path})")
        else:
            print("  (none)")
        remote, err = _remote_available_models()
        print("Remote models (IRCAM API):")
        if remote:
            for m in remote:
                print(f"  {m}")
        else:
            print(f"  (unavailable: {err})")
        sys.exit(0)

    # FR1: ASIO XRun-Prävention – Timer-Resolution + Thread-Priorität
    _init_xrun_prevention()

    # Real-Time-Schutz (AGENTS.md Regel 8, WORKSPACE_AGENT_PROMPT §3.8):
    # Die Inferenz darf sich nie über alle Kerne verteilen und mit dem Audio-
    # Thread kollidieren. Die Kernbegrenzung gilt NUR im CPU-Modus; im GPU-Modus
    # ist das cores-Argument inaktiv (CUDA nutzt keine OpenMP/MKL-Threads).
    if not args.query and not args.gpu:
        args.cores = _limit_inference_threads(args.cores)
    elif args.cores and args.cores != 1:
        print(f"[inference_worker] cores={args.cores} ignored (GPU mode)")

    if args.query:
        query_model(args.model)
        return  # unreachable (query_model calls sys.exit)

    # Debug: print received arguments
    print(f"[inference_worker] Received args: model={args.model}, method={args.method}, bufsize={args.bufsize}, gpu={args.gpu}, n_batches={args.n_batches}, instance_id={args.instance_id}, num_channels={args.num_channels}")
    
    # Generate unique names for this instance
    shm_name = f"MabSharedMem_{args.instance_id:08X}"
    ready_event_name = f"MabReadyEvent_{args.instance_id:08X}"
    
    attrs = RuntimeAttributes()
    streaming_ctx = None

    # -----------------------------------------------------------------------
    #  Load the model FIRST so the shared-memory layout can be sized for the
    #  real method parameters (channels/ratios) before the handshake.
    # -----------------------------------------------------------------------
    model = None
    device = None
    current_model_path = args.model if args.model else ""
    method_params = {}

    if args.model and args.model.strip():
        try:
            model, device = load_model(args.model, bool(args.gpu))
            method_params = get_method_params(model)
        except Exception:
            # Fehler sichtbar machen: landet über die umgeleitete Ausgabe im
            # C++-Log (mab_worker.log). C++ erkennt den Prozess-Tod über den
            # Crash-Monitor und wechselt in den Bypass-Modus.
            print(f"[inference_worker] ERROR loading model '{args.model}':",
                  file=sys.stderr, flush=True)
            traceback.print_exc()
            sys.exit(2)

        print(f"[inference_worker] Model loaded on {device}")
        print(f"[inference_worker] Method params: {method_params}")
    else:
        print("[inference_worker] No model provided - waiting for [load] message")

    # Validate the requested method against what the model actually exposes
    active_method = args.method or "forward"
    if method_params and active_method not in method_params:
        fallback = "forward" if "forward" in method_params else \
            next(iter(method_params), "forward")
        print(f"[inference_worker] Method '{active_method}' not in "
              f"{sorted(method_params)}, using '{fallback}'")
        active_method = fallback

    # -----------------------------------------------------------------------
    #  Compute layout and create shared memory with handshake protocol
    # -----------------------------------------------------------------------
    block_size, max_channels_in, max_channels_out = compute_layout(
        method_params, args.bufsize)
    if not method_params:
        max_channels_in = max_channels_out = args.num_channels
    print(f"[inference_worker] Layout: block_size={block_size}, "
          f"channels_in(max)={max_channels_in}, channels_out(max)={max_channels_out}")

    # Create streaming context for convolutional RAVE models (Bug 1)
    if model is not None and block_size > 0:
        streaming_ctx = ConvStreamingContext(model, block_size)
        if streaming_ctx.active:
            print(f"[inference_worker] ConvStreamingContext active "
                  f"(history={streaming_ctx._context_size} samples)")

    shm = SharedMemoryManager(
        shm_name=shm_name,
        ready_event_name=ready_event_name,
        block_size=block_size,
        channels_in=max_channels_in,
        channels_out=max_channels_out,
        n_batches=args.n_batches
    )

    if not shm.create():
        print("[inference_worker] Failed to create shared memory")
        sys.exit(1)

    # Publish the active method layout (C++ reads this to set up inlets/outlets)
    shm.apply_method(active_method, method_params)

    # Signal C++ that we're ready
    if not shm.signal_ready():
        print("[inference_worker] Failed to signal ready")
        sys.exit(1)

    print(f"[inference_worker] Shared memory created: {shm_name}")
    print(f"[inference_worker] Block size: {block_size}, Method: {active_method}")

    # -----------------------------------------------------------------------
    #  Main loop
    # -----------------------------------------------------------------------
    # Disable automatic GC to avoid multi-millisecond pauses in the inference
    # loop. Collect manually every N processed blocks instead.
    gc.disable()
    gc.collect()  # one clean baseline collection before loop starts
    _block_counter = 0
    _GC_EVERY_N_BLOCKS = 100

    running = True

    while running:
        # Check shutdown flag from C++
        if shm._p_header.shutdown_flag:
            print("[inference_worker] Shutdown flag received.")
            running = False
            break
        
        # Process control messages from C++ via shared memory ring buffer (non-blocking)
        while True:
            head = shm._p_control.head
            tail = shm._p_control.tail
            
            if head == tail:
                # No messages available
                break
            
            # Read message from ring buffer
            idx = tail % CONTROL_RING_SIZE
            msg_bytes = shm._p_control.messages[idx * CONTROL_MSG_SIZE : (idx + 1) * CONTROL_MSG_SIZE]
            msg_str = msg_bytes.split(b'\x00')[0].decode('utf-8', errors='replace')
            
            # Advance tail (consumer)
            shm._p_control.tail = tail + 1
            
            # Parse and handle the message
            parts = msg_str.split()
            if parts:
                cmd = parts[0]
                cmd_args = parts[1:]
                
                if cmd == "enable":
                    if cmd_args and cmd_args[0] == "0":
                        print("[inference_worker] Enable: 0 (bypass)")
                    else:
                        print("[inference_worker] Enable: 1 (active)")
                        if streaming_ctx is not None:
                            streaming_ctx.reset()
                elif cmd == "gpu":
                    # Echter Setter (nn_tilde-Parität P3): Device-Wechsel lädt
                    # das Modell neu; Attribute werden re-applied.
                    if cmd_args:
                        new_gpu = 1 if cmd_args[0] in ("1", "true") else 0
                        old_gpu = args.gpu
                        args.gpu = new_gpu
                        print(f"[inference_worker] GPU mode: {new_gpu}")
                        if new_gpu != old_gpu and model is not None and current_model_path:
                            try:
                                model, device, method_params, active_method, streaming_ctx = _load_and_configure(
                                    current_model_path, bool(args.gpu), active_method,
                                    method_params, attrs, shm, streaming_ctx)
                                print(f"[inference_worker] Model reloaded on {device}")
                            except Exception as e:
                                print(f"[inference_worker] GPU switch failed: {e}")
                        elif new_gpu == 0:
                            # Wechsel zurück auf CPU: Kernbegrenzung (re)aktivieren
                            _limit_inference_threads(args.cores)
                elif cmd == "reload":
                    print("[inference_worker] Reload requested")
                    # Reload model from current path
                    if current_model_path and current_model_path.strip():
                        try:
                            model, device, method_params, active_method, streaming_ctx = _load_and_configure(
                                current_model_path, bool(args.gpu), active_method,
                                method_params, attrs, shm, streaming_ctx)
                            print("[inference_worker] Model reloaded successfully")
                        except Exception as e:
                            print(f"[inference_worker] Reload failed: {e}")
                    else:
                        print("[inference_worker] No model path set, cannot reload")
                elif cmd == "load":
                    # Load a new model
                    if cmd_args:
                        new_model_path = cmd_args[0]
                        print(f"[inference_worker] Loading model: {new_model_path}")
                        try:
                            model, device, method_params, active_method, streaming_ctx = _load_and_configure(
                                new_model_path, bool(args.gpu), active_method,
                                method_params, attrs, shm, streaming_ctx)
                            current_model_path = new_model_path
                            print(f"[inference_worker] Model loaded on {device}")
                        except Exception as e:
                            print(f"[inference_worker] Load failed: {e}")
                    else:
                        print("[inference_worker] Load requires a model path argument")
                elif cmd == "dump":
                    dump_model_info(current_model_path, active_method, device,
                                    attrs.attrs, model, method_params)
                elif cmd == "set":
                    if len(cmd_args) >= 2:
                        msg = attrs.set(cmd_args[0], " ".join(cmd_args[1:]), model=model)
                        print(f"[inference_worker] Set {cmd_args[0]}: {msg}")
                    else:
                        print("[inference_worker] set requires name and value")
                elif cmd == "get":
                    if cmd_args:
                        val = attrs.get(cmd_args[0], model=model)
                        print(f"[inference_worker] Get {cmd_args[0]} = {val}")
                elif cmd == "get_attributes":
                    print("[inference_worker] Available attributes: " +
                          ("; ".join(_list_model_attributes(model, attrs))
                           if _list_model_attributes(model, attrs) else "-"))
                elif cmd == "get_methods":
                    if method_params:
                        print("[inference_worker] Available methods: " +
                              "; ".join(sorted(method_params)))
                    else:
                        print("[inference_worker] Available methods: (no model)")
                elif cmd == "print_available_models":
                    local = list_local_models()
                    print("[inference_worker] Local models:")
                    if local:
                        for fn, path in sorted(local.items()):
                            print(f"  {fn}  ({path})")
                    else:
                        print("  (none)")
                    remote, err = _remote_available_models()
                    print("[inference_worker] Remote models (IRCAM API):")
                    if remote:
                        for m in remote:
                            print(f"  {m}")
                    else:
                        print(f"  (unavailable: {err})")
                elif cmd == "download":
                    if cmd_args:
                        ok, msg = download_model(cmd_args[0],
                                                 cmd_args[1] if len(cmd_args) > 1 else None)
                        print(f"[inference_worker] download: {msg}")
                    else:
                        print("[inference_worker] download requires a model card")
                elif cmd == "delete":
                    if cmd_args:
                        ok, msg = delete_model(cmd_args[0])
                        print(f"[inference_worker] delete: {msg}")
                    else:
                        print("[inference_worker] delete requires a model name")
                elif cmd == "method":
                    if cmd_args:
                        new_method = cmd_args[0]
                        if method_params and new_method in method_params:
                            active_method = new_method
                            shm.apply_method(active_method, method_params)
                            if streaming_ctx is not None:
                                streaming_ctx.reset()
                            print(f"[inference_worker] Method switched: {active_method}")
                        elif method_params:
                            print(f"[inference_worker] Unknown method '{new_method}', "
                                  f"available: {sorted(method_params)}")
                        else:
                            active_method = new_method
                            print(f"[inference_worker] Method: {new_method} (no model yet)")
                else:
                    print(f"[inference_worker] Unknown command: {cmd}")
        
        # Wait for input to be ready (non-blocking check)
        if shm._p_header.is_input_ready:
            # A1: C++ fills header.input_buffer_index; the ready buffer is the other one.
            in_idx = 1 - (shm._p_header.input_buffer_index & 1)
            # C++ drains header.output_buffer_index; write into that same buffer.
            out_idx = shm._p_header.output_buffer_index & 1

            if model is None or active_method not in method_params:
                # No model / no layout - pass through (bypass)
                ibuf = shm.get_numpy_input(in_idx)
                obuf = shm.get_numpy_output(out_idx)
                if shm.n_batches > 1:
                    # Phase 6: per-batch passthrough (batch b -> batch b)
                    n_ch = min(ibuf.shape[1], obuf.shape[1])
                    for b in range(shm.n_batches):
                        obuf[b, :n_ch, :] = ibuf[b, :n_ch, :]
                else:
                    # Phase 5: mc.mab~ publishes the connected per-inlet channel
                    # count; copy exactly those channels through instead of relying
                    # on the (model-less) buffer shape.
                    ci = shm.get_total_input_channels()
                    ci = min(ci, ibuf.shape[0], obuf.shape[0])
                    for ch in range(ci):
                        obuf[ch, :] = ibuf[ch, :]
                shm._p_header.is_output_ready = True
                shm._p_header.is_input_ready = False
            else:
                ci = method_params[active_method][0]
                co = method_params[active_method][2]
                # Phase 5/6: verify the MC wiring against the model layout and log
                # a mismatch once (throttled via _mc_warned). mcs.mab~ expects
                # n_batches * ci total channels (ci per batch inlet).
                expected = ci * shm.n_batches if shm.n_batches > 1 else ci
                connected = shm.get_total_input_channels()
                if connected != expected and connected != int(shm._p_header.channels_in):
                    key = "mc_warned"
                    if getattr(shm, key, False) is False:
                        print(f"[inference_worker] MC wiring: {connected} channel(s) "
                              f"connected, model '{active_method}' expects {expected} "
                              f"({ci} per batch) - unconnected channels are silenced")
                        setattr(shm, key, True)
                elif connected == expected and getattr(shm, "mc_warned", False) is True:
                    setattr(shm, "mc_warned", False)
                try:
                    input_block = shm.get_numpy_input(in_idx, ci)
                    output_block = infer_method(
                        model, device, active_method, method_params, input_block,
                        streaming_context=streaming_ctx, safety_clip=True)
                    out_view = shm.get_numpy_output(out_idx, co)
                    # Phase 6: batched inference returns (B, co, bs); strip the
                    # leading singleton batch dim when writing into the classic
                    # 2-D buffer view (defensive, single-batch mcs).
                    if output_block.ndim == 3 and output_block.shape[0] == 1 \
                            and out_view.ndim == 2:
                        out_view[:, :] = output_block[0]
                    else:
                        out_view[:, :] = output_block
                except Exception:
                    # Bug 4: a GPU/driver error, CUDA OOM or unexpected model
                    # output must NOT crash the worker.  Zero the output block
                    # so the C++ side gets silence instead of stale/corrupt data.
                    out_view = shm.get_numpy_output(out_idx, co)
                    out_view.fill(0.0)
                    traceback.print_exc()
                    print("[inference_worker] Inference error — output zeroed, "
                          "continuing.", flush=True)

                # Signal output is ready
                shm._p_header.is_output_ready = True
                shm._p_header.is_input_ready = False

            _block_counter += 1
            if _block_counter % _GC_EVERY_N_BLOCKS == 0:
                gc.collect()
        
        # A4: Wait for C++ to signal that input is ready, instead of polling.
        # Use a short timeout so shutdown_flag is checked regularly.
        if shm._h_input_ready_event:
            shm.kernel32.WaitForSingleObject(shm._h_input_ready_event, 10)
        else:
            time.sleep(0.001)
    
    # -----------------------------------------------------------------------
    #  Cleanup
    # -----------------------------------------------------------------------
    print("[inference_worker] Shutting down.")
    shm.cleanup()


if __name__ == "__main__":
    main()