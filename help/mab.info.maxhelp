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
    "rect": [100.0, 100.0, 720.0, 480.0],
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
          "text": "mab.info - Model inspector",
          "id": "obj-title",
          "numinlets": 1,
          "numoutlets": 0,
          "patching_rect": [20.0, 20.0, 280.0, 24.0],
          "fontsize": 18.0
        }
      },
      {
        "box": {
          "maxclass": "comment",
          "text": "Arg: [mab.info model.ts]",
          "id": "obj-args",
          "numinlets": 1,
          "numoutlets": 0,
          "patching_rect": [20.0, 55.0, 200.0, 20.0]
        }
      },
      {
        "box": {
          "maxclass": "newobj",
          "text": "mab.info model.ts",
          "id": "obj-info",
          "numinlets": 1,
          "numoutlets": 5,
          "outlettype": ["", "", "", "", ""],
          "patching_rect": [20.0, 210.0, 390.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "comment",
          "text": "Outlets: path | methods | attributes | parameters | dict",
          "id": "obj-outlets",
          "numinlets": 1,
          "numoutlets": 0,
          "patching_rect": [20.0, 185.0, 340.0, 20.0]
        }
      },
      {
        "box": {
          "maxclass": "message",
          "text": "set model.ts",
          "id": "obj-set",
          "numinlets": 2,
          "numoutlets": 1,
          "outlettype": [""],
          "patching_rect": [20.0, 120.0, 80.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "message",
          "text": "bang",
          "id": "obj-bang",
          "numinlets": 2,
          "numoutlets": 1,
          "outlettype": [""],
          "patching_rect": [110.0, 120.0, 40.0, 22.0]
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
          "text": "methods",
          "id": "obj-methods",
          "numinlets": 2,
          "numoutlets": 1,
          "outlettype": [""],
          "patching_rect": [210.0, 120.0, 55.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "message",
          "text": "attributes",
          "id": "obj-attributes",
          "numinlets": 2,
          "numoutlets": 1,
          "outlettype": [""],
          "patching_rect": [275.0, 120.0, 70.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "message",
          "text": "parameters",
          "id": "obj-parameters",
          "numinlets": 2,
          "numoutlets": 1,
          "outlettype": [""],
          "patching_rect": [355.0, 120.0, 75.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "message",
          "text": "dump_dict",
          "id": "obj-dumpdict",
          "numinlets": 2,
          "numoutlets": 1,
          "outlettype": [""],
          "patching_rect": [445.0, 120.0, 70.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "newobj",
          "text": "print path",
          "id": "obj-print-path",
          "numinlets": 1,
          "numoutlets": 0,
          "patching_rect": [20.0, 260.0, 65.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "newobj",
          "text": "print methods",
          "id": "obj-print-methods",
          "numinlets": 1,
          "numoutlets": 0,
          "patching_rect": [110.0, 260.0, 80.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "newobj",
          "text": "print attributes",
          "id": "obj-print-attributes",
          "numinlets": 1,
          "numoutlets": 0,
          "patching_rect": [210.0, 260.0, 90.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "newobj",
          "text": "print params",
          "id": "obj-print-params",
          "numinlets": 1,
          "numoutlets": 0,
          "patching_rect": [320.0, 260.0, 75.0, 22.0]
        }
      },
      {
        "box": {
          "maxclass": "newobj",
          "text": "print dict",
          "id": "obj-print-dict",
          "numinlets": 1,
          "numoutlets": 0,
          "patching_rect": [430.0, 260.0, 65.0, 22.0]
        }
      }
    ],
    "lines": [
      {
        "patchline": {
          "source": ["obj-set", 0],
          "destination": ["obj-info", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-bang", 0],
          "destination": ["obj-info", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-dump", 0],
          "destination": ["obj-info", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-methods", 0],
          "destination": ["obj-info", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-attributes", 0],
          "destination": ["obj-info", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-parameters", 0],
          "destination": ["obj-info", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-dumpdict", 0],
          "destination": ["obj-info", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-info", 0],
          "destination": ["obj-print-path", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-info", 1],
          "destination": ["obj-print-methods", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-info", 2],
          "destination": ["obj-print-attributes", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-info", 3],
          "destination": ["obj-print-params", 0]
        }
      },
      {
        "patchline": {
          "source": ["obj-info", 4],
          "destination": ["obj-print-dict", 0]
        }
      }
    ]
  }
}
