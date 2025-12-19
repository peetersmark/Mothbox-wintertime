"""Small config loader utilities that follow the repo conventions.

Functions here should be safe to call from new scripts and will prefer
external CSV files found under `/media` or `/mnt` before falling back to
the repository defaults (matching existing code behavior).
"""
import csv
import os
from pathlib import Path


def find_external_file(filename, search_paths=("/media", "/mnt"), depth=1):
    """Search top-level of mounted external media for `filename`.

    Returns full path if found, otherwise None.
    """
    for base in search_paths:
        if not os.path.isdir(base):
            continue
        for entry in os.listdir(base):
            candidate = os.path.join(base, entry, filename)
            if os.path.isfile(candidate):
                return candidate
    return None


def read_setting_csv(path, encoding="utf-8"):
    """Read a CSV with headers `SETTING,VALUE,DETAILS` and return dict.

    Non-existing file -> returns empty dict.
    """
    result = {}
    try:
        with open(path, newline="", encoding=encoding) as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row.get("SETTING")
                val = row.get("VALUE")
                if key:
                    result[key] = val
    except FileNotFoundError:
        return {}
    return result


def load_camera_settings(preferred_external=True):
    """Load camera settings. Prefer external media if available.

    Returns a dict of setting->value.
    """
    default = "/home/pi/Desktop/Mothbox/camera_settings.csv"
    if preferred_external:
        ext = find_external_file("camera_settings.csv")
        if ext:
            return read_setting_csv(ext)
    return read_setting_csv(default)


def load_schedule_settings(preferred_external=True):
    default = "/home/pi/Desktop/Mothbox/schedule_settings.csv"
    if preferred_external:
        ext = find_external_file("schedule_settings.csv")
        if ext:
            return read_setting_csv(ext)
    return read_setting_csv(default)


def read_controls(filepath):
    """Read a simple key=value control file into dict. Returns {} if missing."""
    out = {}
    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip()
    except FileNotFoundError:
        return {}
    return out


if __name__ == "__main__":
    # quick manual test
    print("Camera settings (sample):", load_camera_settings(preferred_external=False))
