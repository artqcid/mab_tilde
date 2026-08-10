#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
inference_worker.py

A lock-free, process-isolated backend for MaxMSP objects `mab~` and `mc.mab~`.
It creates shared memory and signals C++ to attach, then exchanges audio blocks
via Windows shared memory with a lock-free SPSC ring buffer for control messages.

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
"""

import sys
import os
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

    Version 2 adds method-aware metadata (channels_in/out, ratios, latent size
    and the active method name) so C++ can set up dynamic inlets/outlets.
    Field order must match the C++ `SharedMemoryHeader` exactly.
    """
    _fields_ = [
        ("magic", ctypes.c_uint32),           # Validation signature 'MABT'
        ("version", ctypes.c_uint32),         # Header version (2)
        ("block_size", ctypes.c_uint32),      # Samples per audio block
        ("num_channels", ctypes.c_uint32),    # Legacy channel count
        ("channels_in", ctypes.c_uint32),     # Method input channels (decode/prior: latent)
        ("channels_out", ctypes.c_uint32),    # Method output channels (encode: latent)
        ("latent_size", ctypes.c_uint32),     # Latent dimension of the active method
        ("input_ratio", ctypes.c_uint32),     # Method input ratio (e.g. RAVE decode: 2048)
        ("output_ratio", ctypes.c_uint32),    # Method output ratio (e.g. RAVE decode: 1)
        ("method", ctypes.c_char * 64),       # Active method name: forward/encode/decode/prior
        ("input_offset", ctypes.c_uint32),    # Byte offset to input buffer
        ("output_offset", ctypes.c_uint32),   # Byte offset to output buffer
        ("control_offset", ctypes.c_uint32),  # Byte offset to control ring buffer
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
                 block_size: int, channels_in: int, channels_out: int):
        """buffers are sized for the MAXIMUM channel counts across all methods,
        so a method switch never needs a shared-memory remap."""
        self.shm_name = shm_name
        self.ready_event_name = ready_event_name
        self.block_size = block_size
        self.channels_in = channels_in
        self.channels_out = channels_out
        
        # Calculate buffer sizes
        self.header_size = ctypes.sizeof(SharedMemoryHeader)
        self.control_size = ctypes.sizeof(ControlRingBuffer)
        self.input_size = block_size * channels_in * 4  # float32 = 4 bytes
        self.output_size = block_size * channels_out * 4
        self.total_size = self.header_size + self.control_size + self.input_size + self.output_size
        
        # Offsets
        self.control_offset = self.header_size
        self.input_offset = self.header_size + self.control_size
        self.output_offset = self.header_size + self.control_size + self.input_size
        
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

        self._h_map = None
        self._p_header = None
        self._p_input = None
        self._p_output = None
        self._p_control = None
        self._h_ready_event = None
        
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
        self._p_header.version = 2
        self._p_header.block_size = self.block_size
        self._p_header.num_channels = self.channels_out
        self._p_header.channels_in = self.channels_in
        self._p_header.channels_out = self.channels_out
        self._p_header.latent_size = 0
        self._p_header.input_ratio = 1
        self._p_header.output_ratio = 1
        self._p_header.method = b"forward"
        self._p_header.input_offset = self.input_offset
        self._p_header.output_offset = self.output_offset
        self._p_header.control_offset = self.control_offset
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
        
        return True
    
    def apply_method(self, method: str, method_params: dict):
        """Publish the active method layout to the header (read by C++)."""
        if not method_params or method not in method_params:
            return
        ci, in_ratio, co, out_ratio = method_params[method]
        self._p_header.method = method.encode('utf-8')[:63]
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
    
    def get_numpy_input(self, channels: int = 0) -> np.ndarray:
        """Get NumPy view of input buffer (zero-copy), sliced to `channels`."""
        if channels <= 0:
            channels = self.channels_in
        # Create a NumPy array that wraps the shared memory
        # Shape: (max_channels_in, block_size)
        arr = np.frombuffer(
            (ctypes.c_float * (self.block_size * self.channels_in)).from_address(
                ctypes.addressof(self._p_input.contents)
            ),
            dtype=np.float32
        )
        return arr.reshape(self.channels_in, self.block_size)[:channels]
    
    def get_numpy_output(self, channels: int = 0) -> np.ndarray:
        """Get NumPy view of output buffer (zero-copy), sliced to `channels`."""
        if channels <= 0:
            channels = self.channels_out
        arr = np.frombuffer(
            (ctypes.c_float * (self.block_size * self.channels_out)).from_address(
                ctypes.addressof(self._p_output.contents)
            ),
            dtype=np.float32
        )
        return arr.reshape(self.channels_out, self.block_size)[:channels]
    
    def cleanup(self):
        """Clean up handles."""
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


def infer_method(model, device, method: str, method_params: dict,
                 input_block: np.ndarray) -> np.ndarray:
    """
    Run one audio block through the model using nn_tilde semantics.

    forward / encode : the full audio block is fed in (channels_in, block_size).
    decode / prior   : only the LAST sample of each channel is taken as the
                       latent frame (nn_tilde `select(-1,-1)` semantics); the
                       output is then held to block_size by repeating frames
                       `output_ratio` times.
    """
    ci, in_ratio, co, out_ratio = method_params[method]
    block_size = input_block.shape[1]

    tensor = torch.from_numpy(np.ascontiguousarray(input_block)).to(device)

    with torch.no_grad():
        if method in ("decode", "prior"):
            z = tensor[:, -1].unsqueeze(0).unsqueeze(-1)  # (1, ci, 1)
            out = getattr(model, method)(z)
        else:
            x = tensor.unsqueeze(0)  # (1, ci, block_size)
            out = getattr(model, method)(x)

    out = out.detach().cpu()
    if out.dim() == 2:
        out = out.unsqueeze(0)   # (1, co, frames)
    if out.dim() < 3:
        out = out.unsqueeze(-1)

    # Hold latent/audio frames: repeat each frame output_ratio times
    out = out.repeat_interleave(out_ratio, dim=-1)

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

    return out[0, :co, :block_size].numpy().astype(np.float32)


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


def _load_and_configure(model_path: str, use_gpu: bool, active_method: str,
                        method_params: dict, attrs: RuntimeAttributes, shm):
    """Load a model, re-validate the method, publish the layout and re-apply
    the runtime attributes. Used by reload / load / gpu switch."""
    model, device = load_model(model_path, use_gpu)
    new_params = get_method_params(model)
    if new_params and active_method not in new_params:
        active_method = "forward" if "forward" in new_params \
            else next(iter(new_params), active_method)
    if shm is not None:
        shm.apply_method(active_method, new_params)
    _reapply_attributes(model, attrs)
    return model, device, new_params, active_method


def main():
    parser = argparse.ArgumentParser(
        description="Python backend for MaxMSP mab~ / mc.mab~"
    )
    parser.add_argument("model", nargs='?', default="", help="Path to the TorchScript model (.ts), or empty for lazy loading")
    parser.add_argument("method", nargs='?', default="forward", help="Default inference method (e.g. forward)")
    parser.add_argument("bufsize", type=int, nargs='?', default=512, help="Audio block size in samples")
    parser.add_argument("gpu", type=int, nargs='?', default=0, help="0 = CPU only, 1 = GPU if available")
    parser.add_argument("shm_name", nargs='?', default="", help="Shared memory name (from C++)")
    parser.add_argument("instance_id", type=int, nargs='?', default=0, help="Process ID for event naming")
    parser.add_argument("num_channels", type=int, nargs='?', default=1, help="Number of audio channels (1 for mab~, up to 16 for mc.mab~)")
    parser.add_argument("cores", type=int, nargs='?', default=1,
                        help="PyTorch inference threads (default 1: prevents the "
                             "all-core thread spread that causes ASIO XRuns)")
    parser.add_argument("--query", action="store_true",
                        help="Inspection mode for mab.info: load the model, print an info block on stdout and exit")
    args = parser.parse_args()

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
    print(f"[inference_worker] Received args: model={args.model}, method={args.method}, bufsize={args.bufsize}, gpu={args.gpu}, instance_id={args.instance_id}, num_channels={args.num_channels}")
    
    # Generate unique names for this instance
    shm_name = f"MabSharedMem_{args.instance_id:08X}"
    ready_event_name = f"MabReadyEvent_{args.instance_id:08X}"
    
    attrs = RuntimeAttributes()

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
        max_channels_in = max_channels_out = num_channels
    print(f"[inference_worker] Layout: block_size={block_size}, "
          f"channels_in(max)={max_channels_in}, channels_out(max)={max_channels_out}")

    shm = SharedMemoryManager(
        shm_name=shm_name,
        ready_event_name=ready_event_name,
        block_size=block_size,
        channels_in=max_channels_in,
        channels_out=max_channels_out
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
                                model, device, method_params, active_method = _load_and_configure(
                                    current_model_path, bool(args.gpu), active_method,
                                    method_params, attrs, shm)
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
                            model, device, method_params, active_method = _load_and_configure(
                                current_model_path, bool(args.gpu), active_method,
                                method_params, attrs, shm)
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
                            model, device, method_params, active_method = _load_and_configure(
                                new_model_path, bool(args.gpu), active_method,
                                method_params, attrs, shm)
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
            if model is None or active_method not in method_params:
                # No model / no layout - pass through (bypass)
                ibuf = shm.get_numpy_input()
                obuf = shm.get_numpy_output()
                ci = min(ibuf.shape[0], obuf.shape[0])
                for ch in range(ci):
                    obuf[ch, :] = ibuf[ch, :]
                shm._p_header.is_output_ready = True
                shm._p_header.is_input_ready = False
            else:
                ci = method_params[active_method][0]
                co = method_params[active_method][2]
                input_block = shm.get_numpy_input(ci)
                output_block = infer_method(
                    model, device, active_method, method_params, input_block)
                shm.get_numpy_output(co)[:, :] = output_block
                
                # Signal output is ready
                shm._p_header.is_output_ready = True
                shm._p_header.is_input_ready = False
        
        # Small yield to avoid 100% CPU
        time.sleep(0.001)
    
    # -----------------------------------------------------------------------
    #  Cleanup
    # -----------------------------------------------------------------------
    print("[inference_worker] Shutting down.")
    shm.cleanup()


if __name__ == "__main__":
    main()