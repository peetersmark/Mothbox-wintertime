#!/usr/bin/env python3
"""rpicam-take.py

Production capture script using `rpicam-still`.

Features implemented per spec:
- Respects OFF/DEBUG pins (16,12). Aborts if OFF active.
- Never toggles relays.
- Uses `winter_camera.csv` (repo template present under `winter_scripts`) to store settings
  and the last used exposure time (stored in microseconds).
- Runs an exposure_time_loop to converge shutter to a target mean brightness using
  multiplicative proportional adjustments, clamped by MinExposure/MaxExposure and
  limited per-iteration by MaxChangeFactor.
- Attempts to lock autos by passing `--analoggain`, `--gain`, and `--awbgains` if present.
- Saves final JPEG and writes a manifest CSV (`rpicam_take_manifest.csv`) in `--out-dir`.
- Retries failing `rpicam-still` calls up to `RetryCount` times.

Usage (examples):
  python3 winter_scripts/rpicam-take.py --dry-run
  python3 winter_scripts/rpicam-take.py --out-dir /home/pi/Desktop/Mothbox/winter_images

Note: exposure times in `winter_camera.csv` are stored in microseconds.

Version: 1.5 - 12-04-2025
Date: 2025-12-04
Changes: Fixed AWB 1.8,1.5 reverted (causing wider cool/warm variation than auto AWB).
         Keeping GammaTransitionError=0.10 for improved convergence.
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time
import shutil
from pathlib import Path

from PIL import Image, ImageStat

# Ensure local package files are importable even when the script is executed
# from a different current working directory (or when the folder name differs).
# This inserts the script's directory at the front of sys.path so `import gpio_safe`
# will load the module bundled alongside this script.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from gpio_safe import setup as gpio_setup, is_off, is_debug

DEFAULT_CAMERA_CSV = os.path.join(os.path.dirname(__file__), "winter_camera.csv")
DEFAULT_OUT_DIR = "/home/pi/Desktop/Mothbox/winter_images"
MANIFEST_NAME = "rpicam_take_manifest.csv"
LOG_PATH = os.path.join(os.path.dirname(__file__), "rpicam-take.log")
# Immediate disabled: do not use --immediate regardless of exposure length


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--camera-csv", default=DEFAULT_CAMERA_CSV, help="Path to winter_camera.csv")
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="Output directory")
    p.add_argument("--dry-run", action='store_true', help="Print commands but don't run rpicam-still")
    p.add_argument("--keep-intermediates", action='store_true', help="Keep intermediate loop images")
    p.add_argument("--width", type=int, help="Override width (px)")
    p.add_argument("--height", type=int, help="Override height (px)")
    return p.parse_args()


def read_camera_csv(path):
    settings = {}
    try:
        with open(path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                k = row.get('SETTING')
                v = row.get('VALUE')
                if k is None:
                    continue
                settings[k] = v if v != '' else None
    except FileNotFoundError:
        return {}
    return settings


def write_camera_csv(path, settings):
    # settings: dict of key->value; write with header SETTING,VALUE,DETAILS
    # Preserve existing DETAILS when possible by reading original file
    details = {}
    rows = []
    if os.path.isfile(path):
        try:
            with open(path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    k = row.get('SETTING')
                    details[k] = row.get('DETAILS', '')
        except Exception:
            pass

    for k, v in settings.items():
        rows.append({'SETTING': k, 'VALUE': '' if v is None else str(v), 'DETAILS': details.get(k, '')})

    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['SETTING', 'VALUE', 'DETAILS'])
        writer.writeheader()
        writer.writerows(rows)


def ensure_out_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def build_rpicam_cmd(out_path, shutter_us, width, height, camera_index=0, analoggain=None, gain=None, awbgains=None, immediate=False):
    timeout_ms = max(5000, int(shutter_us / 1000 + 5000))
    cmd = [
        'rpicam-still', '--camera', str(camera_index), '--width', str(width), '--height', str(height),
        '--shutter', str(int(shutter_us)), '--nopreview', '1', '-t', f"{timeout_ms}ms",
        '-o', str(out_path), '--quality', '95', '--metadata', '-', '--metadata-format', 'json'
    ]
    if immediate:
        cmd.append('--immediate')
    if analoggain is not None:
        cmd += ['--analoggain', str(analoggain)]
    if gain is not None:
        cmd += ['--gain', str(gain)]
    if awbgains is not None:
        cmd += ['--awbgains', str(awbgains)]
    return cmd


def extract_json_from_stdout(stdout):
    try:
        return json.loads(stdout)
    except Exception:
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


def append_manifest(manifest_path, fieldnames, row):
    exists = os.path.isfile(manifest_path)
    with open(manifest_path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def run_capture_command(cmd, dry_run=False):
    if dry_run:
        return {'returncode': 'DRY-RUN', 'stdout': '', 'stderr': ''}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return {'returncode': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr}
    except FileNotFoundError:
        return {'returncode': -1, 'stdout': '', 'stderr': 'rpicam-still not found'}


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def main():
    args = parse_args()

    # Setup GPIO
    try:
        gpio_setup()
    except Exception:
        print('RPi.GPIO not available — continuing in non-hardware mode')

    if is_off():
        print('Mothbox OFF detected — aborting capture')
        # write brief manifest note
        ensure_out_dir(args.out_dir)
        manifest = Path(args.out_dir) / MANIFEST_NAME
        fieldnames = ['timestamp', 'stage', 'filename', 'notes']
        append_manifest(manifest, fieldnames, {'timestamp': time.strftime('%Y-%m-%d-%H-%M-%S'), 'stage': 'abort', 'filename': '', 'notes': 'OFF pin active'})
        return

    settings = read_camera_csv(args.camera_csv)
    # defaults and parsing
    exposure_us = int(settings.get('ExposureTime') or settings.get('ExposureTime', 1000) or 1000)
    analoggain = float(settings.get('AnalogueGain')) if settings.get('AnalogueGain') else None
    gain = float(settings.get('Gain')) if settings.get('Gain') else None
    awbgains_raw = settings.get('AwbGains') if settings.get('AwbGains') else None
    # Validate awbgains: require non-empty and contains a comma, both components non-zero numeric
    awbgains = None
    if awbgains_raw:
        parts = [p.strip() for p in awbgains_raw.split(',')]
        if len(parts) == 2:
            try:
                r_val = float(parts[0])
                b_val = float(parts[1])
                if r_val > 0 and b_val > 0:
                    awbgains = f"{r_val},{b_val}"
            except ValueError:
                awbgains = None
    width = int(settings.get('Width') or 9248)
    height = int(settings.get('Height') or 6944)
    target_mean = float(settings.get('TargetMean') or 100)
    loop_iterations = int(settings.get('LoopIterations') or 5)
    retry_count = int(settings.get('RetryCount') or 2)
    min_exposure = int(settings.get('MinExposure') or 100)
    max_exposure = int(settings.get('MaxExposure') or 240000000)
    tolerance_pct = float(settings.get('TolerancePct') or 5.0)
    max_change = float(settings.get('MaxChangeFactor') or 4.0)
    gamma = float(settings.get('GammaExponent') or 2.2)
    gamma_transition = float(settings.get('GammaTransitionError') or 0.6)

    # allow CLI override for width/height
    if args.width:
        width = args.width
    if args.height:
        height = args.height

    ensure_out_dir(args.out_dir)
    manifest = Path(args.out_dir) / MANIFEST_NAME
    fieldnames = [
        'timestamp', 'stage', 'filename', 'requested_shutter_us', 'requested_analoggain', 'requested_gain', 'requested_awbgains',
        'rpicam_returncode', 'rpicam_stderr', 'metadata_json', 'metadata_exposure_us', 'metadata_analoggain', 'metadata_digitalgain',
        'metadata_awbgains', 'mean_brightness', 'notes'
    ]

    # Exposure loop
    current_exposure = clamp(exposure_us, min_exposure, max_exposure)
    last_mean = None
    last_error = None
    settle_after_flip = 0
    reuse_final = False
    reused_file = None
    reused_metadata = None
    reused_returncode = None
    reused_stderr = ''
    reused_mean = None
    reuse_iteration_stage = ''
    for i in range(1, loop_iterations + 1):
        ts = time.strftime('%Y-%m-%d-%H-%M-%S')
        tmp_name = Path(args.out_dir) / f"rpicam_{ts}_iter{i}.jpg"
        cmd = build_rpicam_cmd(tmp_name, current_exposure, width, height, camera_index=0,
                   analoggain=analoggain, gain=gain, awbgains=awbgains,
                   immediate=False)

        print(f'Iteration {i}: running shutter {current_exposure}us ->', ' '.join(cmd))
        res = run_capture_command(cmd, dry_run=args.dry_run)

        metadata = extract_json_from_stdout(res.get('stdout') or '')
        md_exposure = None
        md_ag = None
        md_dg = None
        md_awb = None
        if metadata:
            md_exposure = metadata.get('ExposureTime') or metadata.get('exp') or metadata.get('shutter')
            md_ag = metadata.get('AnalogueGain') or metadata.get('ag')
            md_dg = metadata.get('DigitalGain') or metadata.get('dg')
            md_awb = metadata.get('AwbGains') or metadata.get('awbgains')

        mean_b = None
        if res.get('returncode') == 0 and tmp_name.is_file():
            mean_b = mean_brightness_jpeg(tmp_name)

        notes = ''
        if res.get('returncode') != 0:
            notes = f"rpicam-still failed (code {res.get('returncode')})"

        append_manifest(manifest, fieldnames, {
            'timestamp': ts, 'stage': f'iter{i}', 'filename': str(tmp_name),
            'requested_shutter_us': current_exposure, 'requested_analoggain': analoggain,
            'requested_gain': gain, 'requested_awbgains': awbgains,
            'rpicam_returncode': res.get('returncode'), 'rpicam_stderr': res.get('stderr'),
            'metadata_json': json.dumps(metadata) if metadata else '', 'metadata_exposure_us': md_exposure,
            'metadata_analoggain': md_ag, 'metadata_digitalgain': md_dg, 'metadata_awbgains': md_awb,
            'mean_brightness': mean_b, 'notes': notes
        })

        # Log brightness & exposure factor to plain log file
        try:
            with open(LOG_PATH, 'a', encoding='utf-8') as lf:
                lf.write(f"{ts} iter{i} exposure_us={current_exposure} mean={mean_b} returncode={res.get('returncode')}\n")
        except Exception:
            pass

        # if dry-run, don't attempt adjustments
        if args.dry_run:
            print('Dry-run mode: skipping exposure adjustments')
            break

        if mean_b is None:
            # capture failed or unreadable; try again in next iteration or exit
            print('Capture failed or mean unknown; will retry loop or exit')
        else:
            last_mean = mean_b
            # check tolerance
            diff_pct = abs(mean_b - target_mean) / target_mean * 100.0 if target_mean > 0 else 0
            if diff_pct <= tolerance_pct:
                print(f'Mean brightness {mean_b} within tolerance {tolerance_pct}% of target {target_mean} -> reusing image')
                final_exposure = current_exposure
                reuse_final = True
                reused_file = tmp_name
                reused_metadata = metadata
                reused_returncode = res.get('returncode')
                reused_stderr = res.get('stderr')
                reused_mean = mean_b
                reuse_iteration_stage = f'iter{i}'
                break
            # Early stop: at MinExposure and still above target -> reuse current image
            if current_exposure <= min_exposure and mean_b > target_mean:
                print('Reached MinExposure while still above target brightness; stopping loop and reusing image')
                final_exposure = current_exposure
                reuse_final = True
                reused_file = tmp_name
                reused_metadata = metadata
                reused_returncode = res.get('returncode')
                reused_stderr = res.get('stderr')
                reused_mean = mean_b
                reuse_iteration_stage = f'iter{i}'
                break
            # Dynamic gamma adjustment bounded by CSV GammaExponent
            error = target_mean - mean_b  # positive => too dark
            norm_error = error / target_mean if target_mean > 0 else 0.0
            abs_norm = abs(norm_error)
            scale = abs_norm / gamma_transition
            if scale < 0:
                scale = 0
            if scale > 1:
                scale = 1
            gamma_dynamic = 1.0 + (gamma - 1.0) * scale
            factor = ((target_mean / mean_b) ** gamma_dynamic) if mean_b > 0 else max_change
            # Overshoot damping: if error sign flips, limit change magnitude for a couple iterations
            if last_error is not None and ((error > 0) != (last_error > 0)):
                settle_after_flip = 2
            if settle_after_flip > 0:
                delta = factor - 1.0
                max_delta = 0.25
                if delta > max_delta:
                    factor = 1.0 + max_delta
                elif delta < -max_delta:
                    factor = 1.0 - max_delta
                settle_after_flip -= 1
            # limit change factor
            factor = clamp(factor, 1.0 / max_change, max_change)
            new_exposure = int(round(current_exposure * factor))
            new_exposure = clamp(new_exposure, min_exposure, max_exposure)
            print(f'Adjusting exposure: {current_exposure} -> {new_exposure} (factor {factor:.3f})')
            # Log factor change
            try:
                with open(LOG_PATH, 'a', encoding='utf-8') as lf:
                    lf.write(f"{ts} iter{i} factor={factor:.3f} new_exposure={new_exposure}\n")
            except Exception:
                pass
            current_exposure = new_exposure
            last_error = error

            # If we've hit max exposure and still below target, stop looping
            if current_exposure >= max_exposure and mean_b < target_mean:
                print('Reached MaxExposure without achieving target brightness; stopping loop early')
                final_exposure = current_exposure
                break

        # optionally remove intermediate
        if not args.keep_intermediates and Path(tmp_name).is_file():
            try:
                Path(tmp_name).unlink()
            except Exception:
                pass

    else:
        # loop exhausted without early break
        final_exposure = current_exposure

    # If dry-run was requested, we already printed commands and should exit
    if args.dry_run:
        print('Dry-run complete — no final capture performed')
        return

    # Final capture with retries
    final_ts = time.strftime('%Y-%m-%d-%H-%M-%S')
    # Prepare final filename with brightness suffix if known
    final_mean_label = None
    if reuse_final and reused_mean is not None:
        final_mean_label = int(round(reused_mean))
    base_final_name = f"rpicam_{final_ts}_ex{final_exposure}us"
    if final_mean_label is not None:
        base_final_name += f"_mean{final_mean_label}"
    final_name = Path(args.out_dir) / (base_final_name + '.jpg')
    # If we are reusing an iteration image, rename/copy instead of capturing again
    if reuse_final and reused_file and reused_file.is_file():
        # Decide rename vs copy
        try:
            if args.keep_intermediates:
                shutil.copy2(reused_file, final_name)
            else:
                reused_file.rename(final_name)
        except Exception:
            pass
        # Append final manifest row using reused data
        append_manifest(manifest, fieldnames, {
            'timestamp': final_ts, 'stage': 'final(reused)', 'filename': str(final_name),
            'requested_shutter_us': final_exposure, 'requested_analoggain': analoggain,
            'requested_gain': gain, 'requested_awbgains': awbgains,
            'rpicam_returncode': reused_returncode,
            'rpicam_stderr': reused_stderr,
            'metadata_json': json.dumps(reused_metadata) if reused_metadata else '',
            'metadata_exposure_us': reused_metadata.get('ExposureTime') if reused_metadata else None,
            'metadata_analoggain': reused_metadata.get('AnalogueGain') if reused_metadata else None,
            'metadata_digitalgain': reused_metadata.get('DigitalGain') if reused_metadata else None,
            'metadata_awbgains': reused_metadata.get('AwbGains') if reused_metadata else None,
            'mean_brightness': reused_mean, 'notes': f'Reused from {reuse_iteration_stage}'
        })
        # Log reuse
        try:
            with open(LOG_PATH, 'a', encoding='utf-8') as lf:
                lf.write(f"{final_ts} final reuse exposure_us={final_exposure} mean={reused_mean}\n")
        except Exception:
            pass
    else:
        final_cmd = build_rpicam_cmd(final_name, final_exposure, width, height, camera_index=0,
                         analoggain=analoggain, gain=gain, awbgains=awbgains,
                         immediate=False)

        attempt = 0
        final_res = None
        while attempt <= retry_count:
            attempt += 1
            print(f'Final capture attempt {attempt}:', ' '.join(final_cmd))
            final_res = run_capture_command(final_cmd, dry_run=args.dry_run)
            if final_res.get('returncode') == 0:
                break
            print('Final capture failed:', final_res.get('stderr'))

        # collect final metadata and mean
        metadata = extract_json_from_stdout(final_res.get('stdout') or '') if final_res else None
        md_exposure = metadata.get('ExposureTime') if metadata else None
        md_ag = metadata.get('AnalogueGain') if metadata else None
        md_dg = metadata.get('DigitalGain') if metadata else None
        md_awb = metadata.get('AwbGains') if metadata else None
        mean_b_final = None
        if final_res and final_res.get('returncode') == 0 and final_name.is_file():
            mean_b_final = mean_brightness_jpeg(final_name)
            if final_mean_label is None and mean_b_final is not None:
                final_mean_label = int(round(mean_b_final))
                renamed = Path(args.out_dir) / f"rpicam_{final_ts}_ex{final_exposure}us_mean{final_mean_label}.jpg"
                try:
                    final_name.rename(renamed)
                    final_name = renamed
                except Exception:
                    pass

        append_manifest(manifest, fieldnames, {
            'timestamp': final_ts, 'stage': 'final', 'filename': str(final_name),
            'requested_shutter_us': final_exposure, 'requested_analoggain': analoggain,
            'requested_gain': gain, 'requested_awbgains': awbgains,
            'rpicam_returncode': final_res.get('returncode') if final_res else 'NO-RESULT',
            'rpicam_stderr': final_res.get('stderr') if final_res else '',
            'metadata_json': json.dumps(metadata) if metadata else '', 'metadata_exposure_us': md_exposure,
            'metadata_analoggain': md_ag, 'metadata_digitalgain': md_dg, 'metadata_awbgains': md_awb,
            'mean_brightness': mean_b_final, 'notes': ''
        })
        # Log final brightness
        try:
            with open(LOG_PATH, 'a', encoding='utf-8') as lf:
                lf.write(f"{final_ts} final exposure_us={final_exposure} mean={mean_b_final} returncode={final_res.get('returncode') if final_res else 'NO-RESULT'}\n")
        except Exception:
            pass

    # update camera csv with new ExposureTime
    settings['ExposureTime'] = str(final_exposure)
    write_camera_csv(args.camera_csv, settings)

    print('Capture complete. Final exposure (us):', final_exposure)


if __name__ == '__main__':
    main()
