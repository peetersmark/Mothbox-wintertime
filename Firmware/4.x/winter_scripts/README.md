# winter_scripts — extension scaffolding

This folder contains new scripts and helpers that extend the Mothbox firmware without modifying the original files.

Overview
- Keep existing repository files untouched. Add new functionality here that reuses CSV formats and GPIO conventions from the main project.

Files
- `config_loader.py` — helpers to read `camera_settings.csv`, `schedule_settings.csv`, and `controls.txt` following the repo's `SETTING,VALUE,DETAILS` convention.
- `gpio_safe.py` — small wrapper for `RPi.GPIO` to centralize `off_pin` / `debug_pin` checks and safe gating of features.
- `sample_capture.py` — example feature script demonstrating safe checks and a dry-run capture flow.
- `requirements.txt` — optional dependencies for the new scripts.

Usage
- Edit or add scripts here. To test on a Pi, run the sample with:

```bash
python3 winter_scripts/sample_capture.py --dry-run
```

Conventions
- Reuse `SETTING,VALUE,DETAILS` CSV layout and `key=value` controls parsing.
- Preserve hardware safety: do not bypass `off_pin` / `debug_pin` checks.

Assumptions for new scripts
- Target Raspberry Pi model: `Pi 5` (all new code may assume Pi5 hardware).
- Camera module: `Arducam 64MP OwlSight OV64A40` (docs: https://docs.arducam.com/Raspberry-Pi-Camera/Native-camera/64MP-OV64A40/).
- Lights/flash: **never** use the ring/flash relays. Do not control `Relay_Ch2` or `Relay_Ch3` from new code (these are intentionally disabled).

These assumptions are encoded in `winter_scripts/defaults.py` and should be referenced by new scripts.

If you want a specific feature added, tell me and I'll scaffold it here following repository patterns.
