"""Example script demonstrating safe capture behaviour for extension scripts.

This script intentionally does not modify repository files. It illustrates the
preferred lifecycle: load settings -> check hardware gates -> (dry-run or) use
Picamera2 to capture -> save to a timestamped file. It respects OFF/DEBUG pins.
"""
import argparse
import time
from pathlib import Path

from config_loader import load_camera_settings, read_controls
from gpio_safe import setup, is_off, is_debug, require_armed
from defaults import USE_LIGHTS, CAMERA_MODULE, CAMERA_DOC_URL, DEFAULT_OUTPUT_DIR


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Don't access camera; just print planned actions")
    p.add_argument("--controls", default="controls.txt", help="Path to controls file")
    p.add_argument("--out-dir", default="/tmp/mothbox_ext", help="Where to write sample output")
    return p.parse_args()


def make_output_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


@require_armed
def do_capture(dry_run, out_dir, controls_path):
    # load repo-style settings
    cam_settings = load_camera_settings(preferred_external=False)
    controls = read_controls(controls_path)

    print("Camera settings summary:", {k: cam_settings.get(k) for k in sorted(list(cam_settings)[:6])})
    print("Control values:", controls)

    if is_debug():
        print("DEBUG pin is active — running in verbose debug mode")

    make_output_dir(out_dir)
    filename = Path(out_dir) / f"sample_{int(time.time())}.txt"

    # Enforce project constraint: lights are disabled for all new code
    if not USE_LIGHTS:
        print("Note: lights/flash relays are disabled for new scripts — not using Relay_Ch2/Relay_Ch3")
    print(f"Assumed camera module: {CAMERA_MODULE} — docs: {CAMERA_DOC_URL}")

    if dry_run:
        print("Dry-run: would call camera with settings and save to:", filename)
        return

    # Try to use picamera2 if available; otherwise fail gracefully.
    try:
        from picamera2 import Picamera2
    except Exception as e:
        print("Picamera2 not available: ", e)
        print("Aborting real capture. Use --dry-run for simulation.")
        return

    picam2 = Picamera2()
    # minimal safe configuration: still capture, small size
    picam2.configure(picam2.create_still_configuration(main={"size": (1024, 768)}))
    picam2.start()
    im = picam2.capture_array()
    picam2.stop()

    # save numpy array to a simple file for example (avoid depending on Pillow here)
    import numpy as np

    np.save(str(filename.with_suffix('.npy')), im)
    print("Saved sample capture to", filename.with_suffix('.npy'))


def main():
    args = parse_args()
    try:
        # setup GPIO if available; will raise on platforms without RPi.GPIO
        setup()
    except Exception:
        print("RPi.GPIO not available — continuing in non-hardware mode")

    if is_off():
        print("Mothbox OFF detected — aborting.")
        return

    do_capture(args.dry_run, args.out_dir, args.controls)


if __name__ == "__main__":
    main()
