#!/usr/bin/env python3
"""Run diagnostic captures using the `rpicam-still` command-line tool.

This script iterates exposure times (seconds) and EV values and invokes
`rpicam-still` for each combination, saving images to the output directory.

It assumes the Arducam 64MP maximum resolution (9248x6944). It sets the
program timeout large enough to accommodate long shutter speeds.

Usage examples:
  python3 rpicam-test.py --single 0.01 -2
  python3 rpicam-test.py --exposure-times 0.01 1 5 --exposure-values -2 2 2 --dry-run
"""
import argparse
import time
import os
from pathlib import Path
import subprocess

DEFAULT_WIDTH = 9248
DEFAULT_HEIGHT = 6944


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--exposure-times", nargs=3, type=float, metavar=("START","END","COUNT"),
                   help="Generate COUNT exposure times between START and END (seconds)")
    p.add_argument("--exposure-values", nargs=3, type=float, metavar=("START","END","STEP"),
                   help="Generate EVs: START END STEP")
    p.add_argument("--single", nargs=2, type=float, metavar=("TIME","EV"),
                   help="Run a single capture with TIME (s) and EV")
    p.add_argument("--out-dir", default=os.environ.get('MOTHBOX_OUT','/tmp/mothbox_ext'),
                   help="Directory to save captures")
    p.add_argument("--camera", type=int, default=0, help="Camera index to pass to rpicam-still")
    p.add_argument("--dry-run", action='store_true', help="Do not call rpicam-still; print commands")
    p.add_argument("--nopreview", action='store_true', help="Pass nopreview to rpicam-still")
    return p.parse_args()


def linspace(start, stop, count):
    if count <= 1:
        return [start]
    step = (stop - start) / (count - 1)
    return [start + i * step for i in range(int(count))]


def frange(start, stop, step):
    vals = []
    if step == 0:
        return [start]
    v = start
    eps = 1e-12
    if step > 0:
        while v <= stop + eps:
            vals.append(v)
            v += step
    else:
        while v >= stop - eps:
            vals.append(v)
            v += step
    return vals


def warn_about_ranges(ev, ex_s):
    notes = []
    if ev < -8.0 or ev > 8.0:
        notes.append(f"EV {ev} outside typical Picamera2 range [-8,8] — may be clamped by driver")
    if ex_s > 30:
        notes.append(f"Exposure {ex_s}s is very long; driver may not support >~30s")
    if ex_s < 1/100:
        notes.append(f"Exposure {ex_s}s shorter than 1/100s; sensor may not reach this in still mode")
    return notes


def ensure_out_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def build_rpicam_cmd(out_path, shutter_s, ev, width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, camera=0, nopreview=False):
    # rpicam-still expects shutter in microseconds when no units provided
    shutter_us = int(round(shutter_s * 1e6))

    # Program timeout (-t) needs to be at least shutter duration (ms) + margin
    timeout_ms = max(5000, int(shutter_s * 1000 + 5000))

    cmd = [
        "rpicam-still",
        "--camera", str(camera),
        "--width", str(width),
        "--height", str(height),
        "--shutter", str(shutter_us),
        "--ev", str(ev),
        "-t", f"{timeout_ms}ms",
        "-o", str(out_path),
        "--quality", "95",
    ]
    if nopreview:
        # help shows --nopreview expects optional arg; pass 1 to enable
        cmd += ["--nopreview", "1"]
    else:
        # ensure no preview by default cli may show preview; pass nopreview anyway
        cmd += ["--nopreview", "1"]
    return cmd


def run_sequence(exposure_times, evs, out_dir, camera_index=0, dry_run=False, nopreview=True):
    ensure_out_dir(out_dir)
    for ex_s in exposure_times:
        for ev in evs:
            notes = warn_about_ranges(ev, ex_s)
            print("---")
            print(f"Planned: shutter={ex_s}s EV={ev} -> warnings: {notes}")

            dt = time.strftime('%Y-%m-%d-%H-%M-%S')
            fname = Path(out_dir) / f"rpicam_{dt}_ex{ex_s:.3f}s_ev{ev:+.2f}.jpg"
            cmd = build_rpicam_cmd(fname, ex_s, ev, camera=camera_index, nopreview=nopreview)

            if dry_run:
                print("DRY-RUN cmd:", " ".join(cmd))
                continue

            print("Running:", " ".join(cmd))
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if proc.returncode != 0:
                    print("rpicam-still returned code", proc.returncode)
                    print("stderr:", proc.stderr)
                else:
                    print("Saved:", fname)
                    if proc.stdout:
                        print(proc.stdout)
            except FileNotFoundError:
                print("rpicam-still not found on PATH. Install it on the Pi and retry.")
                return


def main():
    args = parse_args()

    if args.single:
        ex_s, ev = args.single
        exposure_times = [ex_s]
        evs = [ev]
    else:
        if not args.exposure_times or not args.exposure_values:
            print("Either --single or both --exposure-times and --exposure-values are required")
            return
        s, e, cnt = args.exposure_times
        exposure_times = linspace(s, e, int(cnt))
        evs = frange(args.exposure_values[0], args.exposure_values[1], args.exposure_values[2])

    print("Output dir:", args.out_dir)
    print("Resolution:", DEFAULT_WIDTH, "x", DEFAULT_HEIGHT)

    run_sequence(exposure_times, evs, args.out_dir, camera_index=args.camera, dry_run=args.dry_run, nopreview=args.nopreview)


if __name__ == '__main__':
    main()
