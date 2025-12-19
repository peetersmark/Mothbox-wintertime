#!/usr/bin/env python3
"""Diagnostic Picamera2 tester.

Takes still captures at specified exposure times and exposure values (EV).
This script assumes Raspberry Pi 5 + Arducam 64MP (9248x6944) as project defaults.

Usage examples:
  python3 picam2-test.py --exposure-times 0.01 1 5 --exposure-values -2 2 2
  python3 picam2-test.py --single 0.01 -2

Notes about ranges: see printed diagnostics below — some ranges you asked for
may exceed what libcamera/sensor drivers allow. The script will still attempt
to set controls but will warn when values look out-of-range.
"""
import argparse
import time
from pathlib import Path
import os
import math

DEFAULT_SIZE = (9248, 6944)  # Arducam 64MP OwlSight OV64A40 max resolution


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--exposure-times", nargs=3, type=float, metavar=("START","END","COUNT"),
                   help="Generate COUNT exposure times between START and END (seconds)")
    p.add_argument("--exposure-values", nargs=3, type=float, metavar=("START","END","STEP"),
                   help="Generate exposure value (EV) range: START END STEP (floating)")
    p.add_argument("--single", nargs=2, type=float, metavar=("TIME","EV"),
                   help="Run a single capture with TIME (s) and EV")
    p.add_argument("--out-dir", default=os.environ.get('MOTHBOX_OUT', '/tmp/mothbox_ext'),
                   help="Output directory")
    p.add_argument("--dry-run", action='store_true', help="Do not access camera; print planned actions")
    p.add_argument("--wait", type=float, default=0.5, help="Seconds to wait after setting controls before capture")
    return p.parse_args()


def frange(start, stop, step):
    vals = []
    v = start
    eps = 1e-12
    if step == 0:
        return [start]
    if step > 0:
        while v <= stop + eps:
            vals.append(v)
            v += step
    else:
        while v >= stop - eps:
            vals.append(v)
            v += step
    return vals


def linspace(start, stop, count):
    if count <= 1:
        return [start]
    step = (stop - start) / (count - 1)
    return [start + i * step for i in range(int(count))]


def warn_about_ranges(ev, exptime_s):
    notes = []
    # Based on existing code in this repo and Picamera2/libcamera doc snippets:
    # - ExposureValue (EV) in this codebase is normally limited to about -8.0 .. 8.0
    #   (TakePhoto.py comments and usage). Values outside that range may be clamped
    #   by libcamera or ignored by the sensor driver.
    if ev < -8.0 or ev > 8.0:
        notes.append(f"EV {ev} outside typical Picamera2 range [-8,8] — may be clamped")

    # ExposureTime in libcamera controls is in microseconds. Many sensors/drivers
    # limit max exposure time (often to a few seconds); extremely long exposures
    # like 1000s (16+ minutes) are unlikely to be supported in hardware by the
    # default mode and may require special sensor modes or firmware support.
    if exptime_s > 30:
        notes.append(f"Exposure {exptime_s}s is very long; sensor/driver may not support >~30s")
    if exptime_s < 1/100:
        notes.append(f"Exposure {exptime_s}s shorter than 1/100s; sensor may not reach very high frame-rate in still mode")

    return notes


def ensure_out_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def run_capture_sequence(exposure_times_s, evs, out_dir, dry_run=False, wait=0.5):
    ensure_out_dir(out_dir)

    try:
        from picamera2 import Picamera2
    except Exception as e:
        print("Picamera2 not available:", e)
        print("Install picamera2 on the Pi and run this script there, or use --dry-run.")
        return

    picam2 = Picamera2()

    # Configure with the large still size. This may fail if the camera driver
    # does not support that configuration; we attempt it and will report errors.
    try:
        still_conf = picam2.create_still_configuration(main={"size": DEFAULT_SIZE, "format": "RGB888"})
        picam2.configure(still_conf)
    except Exception as e:
        print("Failed to configure Picamera2 with size", DEFAULT_SIZE, "->", e)
        print("Try a smaller size or verify camera driver supports 9248x6944")
        return

    for ex_s in exposure_times_s:
        for ev in evs:
            notes = warn_about_ranges(ev, ex_s)
            print("---")
            print(f"Planned capture: exposure={ex_s}s, EV={ev}")
            for n in notes:
                print("WARN:", n)

            if dry_run:
                print("Dry-run: skip hardware capture")
                continue

            # Convert exposure time to microseconds for libcamera control
            ex_us = int(round(ex_s * 1e6))

            # Use manual exposure: disable AE then set ExposureTime and AnalogueGain/ExposureValue
            # Note: some drivers require specific sequences; libcamera may clamp values.
            try:
                picam2.start()
                picam2.set_controls({
                    "AeEnable": False,
                    "ExposureTime": ex_us,
                    # Picamera2 doesn't expose a single 'ExposureValue' control universally;
                    # the repo uses an 'ExposureValue' float for relative exposure adjustments.
                    # We'll attempt to set 'ExposureValue' if supported, otherwise skip.
                    "ExposureValue": float(ev),
                })
                # small settle time
                time.sleep(wait)
                ts = int(time.time())
                fname = Path(out_dir) / f"picam2_test_ex{ex_s:.3f}s_ev{ev:+.2f}_{ts}.jpg"
                # capture_file will request a still capture to the given path
                picam2.capture_file(str(fname))
                print("Captured ->", fname)
            except Exception as e:
                print("Capture failed:", e)
            finally:
                try:
                    picam2.stop()
                except Exception:
                    pass


def main():
    args = parse_args()

    if args.single:
        ex, ev = args.single
        exposure_times = [ex]
        evs = [ev]
    else:
        if not args.exposure_times or not args.exposure_values:
            print("Either --single or both --exposure-times and --exposure-values are required")
            return
        start, end, count = args.exposure_times
        exposure_times = linspace(start, end, int(count))
        ev_start, ev_end, ev_step = args.exposure_values
        evs = frange(ev_start, ev_end, ev_step)

    print("Using resolution:", DEFAULT_SIZE)
    print("Planned exposure times (s):", exposure_times)
    print("Planned EVs:", evs)

    # High-level warnings about user-requested ranges
    print("\nRange notes:")
    print("- ExposureValue typically supported in Picamera2/libcamera around -8..8 (repo evidence).")
    print("- ExposureTime is set in microseconds via the 'ExposureTime' control; sensors/drivers often limit max exposure (many sensors cap at a few seconds).")
    print("- Extremely long exposures (tens to thousands of seconds) are likely unsupported without special sensor modes or firmware. These may fail or be clamped.")

    run_capture_sequence(exposure_times, evs, args.out_dir, dry_run=args.dry_run, wait=args.wait)


if __name__ == '__main__':
    main()
