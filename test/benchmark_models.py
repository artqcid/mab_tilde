#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T7 – Benchmark-Report (Standalone-Tool, kein pytest).

Misst CPU- und GPU-Latenzen fuer alle TorchScript-Modelle und gibt eine
Markdown-Tabelle aus. Mit `--report <datei>` wird die Messung als neuer,
fortlaufend nummerierter **Testrun** (mit Datum) oben in eine Report-Datei
(Standard: doc/benchmark_reports.md) eingefuegt.

Verwendung:
    .venv\\Scripts\\python test/benchmark_models.py                        # CPU + GPU, stdout
    .venv\\Scripts\\python test/benchmark_models.py --cpu-only
    .venv\\Scripts\\python test/benchmark_models.py --gpu-only
    .venv\\Scripts\\python test/benchmark_models.py --runs 50 --warmup 5
    .venv\\Scripts\\python test/benchmark_models.py --report doc/benchmark_reports.md
    .venv\\Scripts\\python test/benchmark_models.py --report doc/benchmark_reports.md --note "Test nach Fix"

ONNX-Modelle (`*_onnx.ts`) werden mit "nicht unterstuetzt" vermerkt.
AFTER-v2 (`afterv2.audio.instr.ts`) wird ausgelassen (RAM > 10 GB).
"""

import argparse
import gc
import glob
import os
import re
import sys
import time

import numpy as np
import torch

# Windows-Konsole: UTF-8, damit Umlaute in der Markdown-Ausgabe stimmen
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference_worker import (
    compute_layout,
    get_method_params,
    infer_method,
    load_model,
)

MODEL_DIR = r"D:\AI-Models\ts models"
ONNX_SKIP_SUFFIX = "_onnx.ts"
SKIP_MODELS = {"afterv2.audio.instr.ts"}
DEFAULT_REPORT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "doc", "benchmark_reports.md")

torch.set_num_threads(4)


def model_files():
    files = [f for f in glob.glob(os.path.join(MODEL_DIR, "*.ts"))
             if os.path.basename(f) not in SKIP_MODELS]
    return sorted(files)


def _cleanup():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def benchmark_infer(model, device, method, params, input_block,
                    warmup=5, runs=50):
    """Durchschnittliche Inferenzzeit in ms pro Block."""
    for _ in range(warmup):
        infer_method(model, device, method, params, input_block)
    if device.type == "cuda":
        torch.cuda.synchronize()

    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        infer_method(model, device, method, params, input_block)
        if device.type == "cuda":
            torch.cuda.synchronize()
        times.append(time.perf_counter() - t0)

    return {
        "mean_ms": float(np.mean(times) * 1000),
        "std_ms": float(np.std(times) * 1000),
        "min_ms": float(np.min(times) * 1000),
        "max_ms": float(np.max(times) * 1000),
    }


def bench_model(path, device, warmup, runs, method_hint="forward"):
    """Laedt ein Modell und misst die angefragte Methode (oder die erste)."""
    model, dev = load_model(path, use_gpu=(device == "cuda"))
    try:
        params = get_method_params(model)
        if not params:
            return {"methods": 0}
        method = method_hint if method_hint in params else sorted(params)[0]
        ci, _ri, _co, _ro = params[method]
        bs = compute_layout(params, 512)[0]
        rng = np.random.default_rng(0)
        inp = rng.uniform(-1.0, 1.0, size=(ci, bs)).astype(np.float32)
        res = benchmark_infer(model, dev, method, params, inp,
                              warmup=warmup, runs=runs)
        res.update({"method": method, "ci": ci, "bs": bs,
                    "methods": len(params)})
        return res
    finally:
        del model
        _cleanup()


def _next_run_number(report_path):
    """Findet die naechste Testrun-Nummer aus der Report-Datei (Testrun NNN)."""
    try:
        with open(report_path, encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return 1
    nums = [int(m) for m in re.findall(r"Testrun (\d{3,})", content)]
    return (max(nums) + 1) if nums else 1


def _device_line(args):
    _dev = (torch.cuda.get_device_name(0) if torch.cuda.is_available()
            else "CPU only")
    modes = []
    if not args.gpu_only:
        modes.append("CPU")
    if not args.cpu_only and torch.cuda.is_available():
        modes.append("GPU")
    return ("_Gerät: %s | Runs=%d Warmup=%d | Methode: `%s` | Messung: %s_"
            % (_dev, args.runs, args.warmup, args.method, "+".join(modes)))


def append_run_to_report(report_path, args, rows, notes):
    """Fuegt die Messung als neuen nummerierten Testrun oben ein."""
    run_no = _next_run_number(report_path)
    date = time.strftime("%Y-%m-%d")
    title = "## Testrun %03d – %s" % (run_no, date)
    if args.note:
        title += " (%s)" % args.note

    block = [title, ""]
    block.append(_device_line(args))
    block.append("")
    header = ("| Modell | Größe | Methoden | Block | CPU ms | GPU ms | "
              "GPU/CPU |")
    sep = ("|--------|-------|----------|-------|--------|--------|"
           "---------|")
    block.append(header)
    block.append(sep)
    block.extend(rows)
    block.append("")
    if notes:
        block.append("**Anmerkungen:** %s" % " ".join(notes))
        block.append("")
    block.append("---")
    block.append("")

    # Report-Datei: neue Messung NACH der Kopfzeile einfuegen (neueste oben)
    try:
        with open(report_path, encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        content = ""
    if not content:
        content = ("# mab~ Benchmark-Reports\n\n"
                   "_Gesammelte Messungen aus `test/benchmark_models.py`._\n\n"
                   "---\n\n")
    marker = "---\n\n"
    idx = content.find(marker)
    if idx != -1:
        idx += len(marker)
        content = content[:idx] + "\n".join(block) + "\n" + content[idx:]
    else:
        content += "\n".join(block) + "\n"

    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return run_no


def main():
    ap = argparse.ArgumentParser(description="mab~ Benchmark-Report")
    ap.add_argument("--cpu-only", action="store_true")
    ap.add_argument("--gpu-only", action="store_true")
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--method", default="forward",
                    help="Methoden-Hinweis (fallback: erste Methode)")
    ap.add_argument("--report", nargs="?", const=DEFAULT_REPORT,
                    default=None,
                    help="Report-Datei fuer neuen Testrun-Eintrag "
                         "(default: %s)" % DEFAULT_REPORT)
    ap.add_argument("--note", default="",
                    help="Optionaler Notiztext fuer den Testrun (z.B. "
                         "'nach Fix X')")
    args = ap.parse_args()

    do_cpu = not args.gpu_only
    do_gpu = (not args.cpu_only) and torch.cuda.is_available()

    files = model_files()
    if not files:
        print("Keine Modelle gefunden in %s" % MODEL_DIR)
        return 1

    print("# mab~ Benchmark (%s)" % time.strftime("%Y-%m-%d"))
    print()
    print(_device_line(args))
    print()

    header = ("| Modell | Größe | Methoden | Block | CPU ms | GPU ms | "
              "GPU/CPU |")
    sep = ("|--------|-------|----------|-------|--------|--------|"
           "---------|")
    print(header)
    print(sep)

    rows = []
    notes = []
    for path in files:
        name = os.path.basename(path)
        size_mb = os.path.getsize(path) / 1024 / 1024
        if name.lower().endswith(ONNX_SKIP_SUFFIX):
            line = "| `%s` | %.1f MB | ONNX | – | – | – | – |" % (name, size_mb)
            print(line)
            rows.append(line)
            continue
        if name in SKIP_MODELS:
            line = ("| `%s` | %.1f MB | – | – | nicht unterstuetzt | – | – |"
                    % (name, size_mb))
            print(line)
            rows.append(line)
            continue

        cells = ["`%s`" % name, "%.1f MB" % size_mb]
        cpu_ms = gpu_ms = ratio = None
        try:
            if do_cpu:
                r = bench_model(path, "cpu", args.warmup, args.runs, args.method)
                cells += ["%d" % r["methods"], "%d" % r["bs"],
                          "**%.3f**" % r["mean_ms"]]
                cpu_ms = r["mean_ms"]
            else:
                cells += ["–", "–", "–"]
        except Exception as exc:
            cells += ["–", "–", "CPU-Fehler"]
            notes.append("%s: CPU-Fehler (%s)" % (name, str(exc)[:40]))

        try:
            if do_gpu:
                r = bench_model(path, "cuda", args.warmup, args.runs, args.method)
                gpu_ms = r["mean_ms"]
                ratio = gpu_ms / cpu_ms if cpu_ms else None
                gpu_txt = "**%.3f**" % gpu_ms
            else:
                gpu_txt = "–"
            cells.append(gpu_txt)
        except Exception as exc:
            cells.append("GPU-Fehler")
            notes.append("%s: GPU-Fehler (%s)" % (name, str(exc)[:40]))

        if ratio is not None:
            cells.append("%.2fx" % ratio)
        else:
            cells.append("–")
        line = "| %s |" % " | ".join(cells)
        print(line)
        rows.append(line)
        sys.stdout.flush()

    print()
    print("_ONNX (`darbouka_onnx.ts`) wird nicht unterstuetzt; "
          "AFTER-v2 (`afterv2.audio.instr.ts`) wegen RAM > 10 GB ausgelassen._")

    if args.report:
        run_no = append_run_to_report(args.report, args, rows, notes)
        print()
        print("→ Als %s als Testrun %03d eingetragen."
              % (args.report, run_no))
    return 0


if __name__ == "__main__":
    sys.exit(main())

