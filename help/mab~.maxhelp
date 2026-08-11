{
  "patcher": {
    "fileversion": 1,
    "appversion": {
      "major": 9,
      "minor": 0,
      "revision": 0,
      "architecture": "x64",
      "modernui": 1
    },
    "classnamespace": "box",
    "rect": [100.0, 100.0, 720.0, 560.0],
    "bglocked": 0,
    "openinpresentation": 0,
    "default_fontsize": 12.0,
    "default_fontface": 0,
    "default_fontname": "Arial",
    "gridonopen": 1,
    "gridsize": [15.0, 15.0],
    "showontab": 1,
    "boxes": [
      {
        "box": {
          "maxclass": "comment",
          "text": "mab~ - RAVE / AFTER TorchScript inference",
          "id": "obj-title",
          "numinlets": 1,
          "numoutlets": 0,
          "patching_rect": [20.0, 20.0, 320.0, 24.0],
          "fontsize": 18.0
        }
      },
      {
        "box": {
          "maxclass": "comment",
          "text": "Args: [mab~ model.ts (method) (buffer_size) (gpu) (num_channels) (cores)]",
          "id": "obj-args",
          "numinlets": 1,
          "numoutlets": 0,
          "patching_rect": [20.0, 55.0, 460.0, 20.0]
        }
      },
      {
        "box": {
          "maxclass": "newobj",
          "text": "mab~ model.ts forward 512 0 1 2",
          "id": "obj-mab",
          "numinlets": 1,
          "numoutlets": 1,
          "patching_rect": [20.0, 210.0, 210.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "comment",
          "text": "Replace model.ts with your own TorchScript file.",
          "id": "obj-model-note",
          "numinlets": 1,
          "numoutlets": 0,
          "patching_rect": [240.0, 210.0, 260.0, 20.0]
        }
      },
      {
        "box": {
          "maxclass": "message",
          "text": "enable 0",
          "id": "obj-enable0",
          "numinlets": 2,
          "numoutlets": 1,
          "outlettype": [""],
          "patching_rect": [20.0, 120.0, 60.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "message",
          "text": "enable 1",
          "id": "obj-enable1",
          "numinlets": 2,
          "numoutlets": 1,
          "outlettype": [""],
          "patching_rect": [90.0, 120.0, 60.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "message",
          "text": "dump",
          "id": "obj-dump",
          "numinlets": 2,
          "numoutlets": 1,
          "outlettype": [""],
          "patching_rect": [160.0, 120.0, 40.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "message",
          "text": "method encode",
          "id": "obj-method-encode",
          "numinlets": 2,
          "numoutlets": 1,
          "outlettype": [""],
          "patching_rect": [210.0, 120.0, 90.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "message",
          "text": "reload",
          "id": "obj-reload",
          "numinlets": 2,
          "numoutlets": 1,
          "outlettype": [""],
          "patching_rect": [310.0, 120.0, 45.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "message",
          "text": "load model.ts",
          "id": "obj-load",
          "numinlets": 2,
          "numoutlets": 1,
          "outlettype": [""],
          "patching_rect": [370.0, 120.0, 85.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "comment",
          "text": "Messages",
          "id": "obj-msg-label",
          "numinlets": 1,
          "numoutlets": 0,
          "patching_rect": [20.0, 95.0, 80.0, 20.0],
          "fontface": 1
        }
      },
      {
        "box": {
          "maxclass": "comment",
          "text": "Audio input (cycle~ as placeholder)",
          "id": "obj-audio-label",
          "numinlets": 1,
          "numoutlets": 0,
          "patching_rect": [20.0, 165.0, 200.0, 20.0]
        }
      },
      {
        "box": {
          "maxclass": "newobj",
          "text": "cycle~ 440",
          "id": "obj-cycle",
          "numinlets": 2,
          "numoutlets": 1,
          "outlettype": ["signal"],
          "patching_rect": [20.0, 185.0, 65.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "newobj",
          "text": "live.gain~",
          "id": "obj-gain",
          "numinlets": 2,
          "numoutlets": 5,
          "outlettype": ["signal", "signal", "", "float", "list"],
          "patching_rect": [20.0, 250.0, 70.0, 48.0]
        }
      },
      {
        "box": {
          "maxclass": "newobj",
          "text": "ezdac~",
          "id": "obj-dac",
          "numinlets": 2,
          "numoutlets": 0,
          "patching_rect": [20.0, 320.0, 45.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "comment",
          "text": "Methods: forward (default), encode, decode, prior. IO rebuilds automatically.",
          "id": "obj-methods-note",
          "numinlets": 1,
          "numoutlets": 0,
          "patching_rect": [20.0, 370.0, 420.0, 20.0]
        }
      },
      {
        "box": {
          "maxclass": "comment",
          "text": "Void mode: mab~ void <inlets> <outlets> <bufsize>",
          "id": "obj-void-note",
          "numinlets": 1,
          "numoutlets": 0,
          "patching_rect": [20.0, 400.0, 320.0, 20.0]
        }
      }
    ],
    "lines": [
      {
        "patchline": {
          "source": ["obj-cycle", 0],
          "destination": ["obj-mab", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-mab", 0],
          "destination": ["obj-gain", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-gain", 0],
          "destination": ["obj-dac", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-gain", 1],
          "destination": ["obj-dac", 1]
        }
      },
      {
        "patchline": {
          "source": ["obj-enable0", 0],
          "destination": ["obj-mab", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-enable1", 0],
          "destination": ["obj-mab", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-dump", 0],
          "destination": ["obj-mab", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-method-encode", 0],
          "destination": ["obj-mab", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-reload", 0],
          "destination": ["obj-mab", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-load", 0],
          "destination": ["obj-mab", 0]
        }
      }
    ]
  }
}
