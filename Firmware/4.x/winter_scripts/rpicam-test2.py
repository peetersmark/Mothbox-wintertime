#!/usr/bin/env python3
"""rpicam-test2.py

Calls `rpicam-still` for combinations of shutter and EV, captures JSON metadata,
computes mean JPEG brightness, and writes a CSV manifest per capture. Attempts
to lock auto settings by passing fixed gain and AWB when requested.

JPEG only (no RAW). CSV columns include timestamp, filename, requested values,
actual metadata (as JSON) and derived mean_brightness.
"""
import argparse
import csv
import json
import os
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageStat

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
    p.add_argument("--analoggain", type=float, default=None, help="Fix analog gain (sets --analoggain)")
    p.add_argument("--gain", type=float, default=None, help="Fix gain (sets --gain)")
    p.add_argument("--awbgains", type=str, default=None, help="Fix AWB gains as 'R,G' (sets --awbgains)")
    p.add_argument("--manifest", default='rpicam_manifest.csv', help="CSV manifest path (appended)")
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


def ensure_out_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def build_rpicam_cmd(out_path, shutter_s, ev, width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, camera=0, nopreview=True,
                     analoggain=None, gain=None, awbgains=None):
    shutter_us = int(round(shutter_s * 1e6))
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
        "--metadata", "-",
        "--metadata-format", "json",
    ]

    # try to suppress preview
    cmd += ["--nopreview", "1"] if nopreview else []

    if analoggain is not None:
        cmd += ["--analoggain", str(analoggain)]
    if gain is not None:
        cmd += ["--gain", str(gain)]
    if awbgains is not None:
        cmd += ["--awbgains", str(awbgains)]

    return cmd


def extract_json_from_stdout(stdout):
    try:
        return json.loads(stdout)
    except Exception:
        # try to extract first {...} block
        start = stdout.find('{')
        end = stdout.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(stdout[start:end+1])
            except Exception:
                return None
        return None


def mean_brightness_jpeg(path):
    try:
        im = Image.open(path).convert('L')
        stat = ImageStat.Stat(im)
        return float(stat.mean[0])
    except Exception:
        return None


def append_manifest(manifest_path, row, fieldnames):
    exists = os.path.isfile(manifest_path)
    with open(manifest_path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def run_sequence(exposure_times, evs, out_dir, args):
    ensure_out_dir(out_dir)
    manifest = Path(out_dir) / args.manifest
    # manifest columns
    fieldnames = [
        'timestamp', 'filename', 'requested_shutter_s', 'requested_ev', 'requested_analoggain', 'requested_gain', 'requested_awbgains',
        'rpicam_returncode', 'rpicam_stderr', 'metadata_json', 'metadata_exposure_us', 'metadata_analoggain', 'metadata_digitalgain',
        'metadata_awbgains', 'mean_brightness'
    ]

    for ex_s in exposure_times:
        for ev in evs:
            ts = time.strftime('%Y-%m-%d-%H-%M-%S')
            fname = Path(out_dir) / f"rpicam_{ts}_ex{ex_s:.3f}s_ev{ev:+.2f}.jpg"
            cmd = build_rpicam_cmd(fname, ex_s, ev, camera=args.camera, nopreview=True,
                                   analoggain=args.analoggain, gain=args.gain, awbgains=args.awbgains)

            print('---')
            print('Planned:', ' '.join(cmd))
            if args.dry_run:
                # write empty/placeholder manifest row for dry-run
                row = {
                    'timestamp': ts,
                    'filename': str(fname),
                    'requested_shutter_s': ex_s,
                    'requested_ev': ev,
                    'requested_analoggain': args.analoggain,
                    'requested_gain': args.gain,
                    'requested_awbgains': args.awbgains,
                    'rpicam_returncode': 'DRY-RUN',
                    'rpicam_stderr': '',
                    'metadata_json': '',
                    'metadata_exposure_us': '',
                    'metadata_analoggain': '',
                    'metadata_digitalgain': '',
                    'metadata_awbgains': '',
                    'mean_brightness': ''
                }
                append_manifest(manifest, row, fieldnames)
                continue

            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            except FileNotFoundError:
                print('rpicam-still not found on PATH. Install it on the Pi and retry.')
                return

            metadata = extract_json_from_stdout(proc.stdout or '')

            metadata_exposure_us = None
            metadata_analoggain = None
            metadata_digitalgain = None
            metadata_awb = None
            if metadata:
                # try common keys
                metadata_exposure_us = metadata.get('ExposureTime') or metadata.get('exp') or metadata.get('shutter')
                metadata_analoggain = metadata.get('AnalogueGain') or metadata.get('ag')
                metadata_digitalgain = metadata.get('DigitalGain') or metadata.get('dg')
                # awb gains may be returned under different keys
                metadata_awb = metadata.get('AwbGains') or metadata.get('awbgains') or None

            mean_b = None
            if proc.returncode == 0 and Path(fname).is_file():
                mean_b = mean_brightness_jpeg(fname)

            row = {
                'timestamp': ts,
                'filename': str(fname),
                'requested_shutter_s': ex_s,
                'requested_ev': ev,
                'requested_analoggain': args.analoggain,
                'requested_gain': args.gain,
                'requested_awbgains': args.awbgains,
                'rpicam_returncode': proc.returncode,
                'rpicam_stderr': (proc.stderr or '').strip(),
                'metadata_json': json.dumps(metadata) if metadata is not None else '',
                'metadata_exposure_us': metadata_exposure_us,
                'metadata_analoggain': metadata_analoggain,
                'metadata_digitalgain': metadata_digitalgain,
                'metadata_awbgains': metadata_awb,
                'mean_brightness': mean_b
            }

            append_manifest(manifest, row, fieldnames)
            print('Wrote manifest row for', fname)


def main():
    args = parse_args()

    if args.single:
        ex_s, ev = args.single
        exposure_times = [ex_s]
        evs = [ev]
    else:
        if not args.exposure_times or not args.exposure_values:
            print('Either --single or both --exposure-times and --exposure-values are required')
            return
        s, e, cnt = args.exposure_times
        exposure_times = linspace(s, e, int(cnt))
        evs = frange(args.exposure_values[0], args.exposure_values[1], args.exposure_values[2])

    print('Output dir:', args.out_dir)
    ensure_out_dir(args.out_dir)
    run_sequence(exposure_times, evs, args.out_dir, args)


if __name__ == '__main__':
    main()
