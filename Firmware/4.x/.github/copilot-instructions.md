<!-- Copilot / AI agent instructions for Mothbox-wintertime Firmware (4.x) -->
# Mothbox-wintertime — AI coding guidance

This file gives focused, actionable guidance for AI coding agents working in this repository. Keep suggestions specific to the code here (don't add generic or aspirational rules).

1. Big picture
- Purpose: Raspberry Pi-based camera controller for the "Mothbox" — scheduled/triggered imaging, power-management, and small display integration.
- Major components:
  - Top-level scripts (e.g. `TakePhoto.py`, `Scheduler.py`, `UpdateDisplay.py`) implement main behaviours.
  - `scripts/` contains utilities and variants (autofocus helpers, flash control, helpers for different photo modes).
  - `scripts/MothPower/` contains systemd/timer and shell helpers for low-power management (`lowpower.service`, `lowpower.timer`, `lowpower.sh`).
  - `scripts/RaspberryPi_JetsonNano_Epaper/` embeds Waveshare e-paper library code used by `UpdateDisplay.py` and other display helpers.
  - `crontab_examples/` stores example crontab files used to boot/schedule actions on the device.

2. Key dataflows & file formats
- Camera and schedule configuration are CSVs with headers. Typical CSV rows use columns `SETTING,VALUE,DETAILS` (see `camera_settings.csv`, `schedule_settings.csv`).
- `controls.txt` (or `controls.txt`-like files) are simple `key=value` lines read by `get_control_values()` across scripts.
- External storage detection: code looks under `/media` and `/mnt` for updated CSVs and chooses them over the internal defaults.

3. Hardware and platform conventions
- Target platform: Raspberry Pi (Pi4 / Pi5). Many scripts guard behavior depending on Pi model (see `Scheduler.determinePiModel()`).
- Camera: uses `picamera2` / `libcamera` APIs (`from picamera2 import Picamera2`) and manipulates controls via `picam2.set_controls(...)`. Look for `capture_metadata()` usage and `autofocus_cycle()` patterns.
- GPIO: uses `RPi.GPIO` for relay/flash and mode pins. Common pattern: set `GPIO.setmode(GPIO.BCM)`, then check `off_pin` (16) and `debug_pin` (12) to decide `OFF/DEBUG/ARMED` mode (see `TakePhoto.py`).

4. Dependencies discovered in-code
- Python packages referenced: `picamera2`, `libcamera`, `RPi.GPIO`, `gpiozero` (in e-paper helper), `opencv-python` (`cv2`), `numpy`, `PIL`/`Pillow`, `piexif`, `schedule`, `python-crontab`.
- System integration: uses `sudo rpi-eeprom-config`, `service cron start/stop`, and systemd unit files in `scripts/MothPower/`.

5. Common code patterns to follow in patches
- CSV settings readers: prefer the repository's `csv.DictReader`/`SETTING,VALUE,DETAILS` convention and preserve fallback logic that checks `/media` and `/mnt`.
- Control files: parse `key=value` lines with `get_control_values(filepath)` used by many scripts. When editing, maintain strict `key=value` format.
- Camera control: when changing capture behavior, follow the existing lifecycle: load settings -> configure Picamera2 -> (optional) run autofocus/calibration -> flashOn() -> capture -> flashOff() -> save with EXIF via `piexif`.
- Power management: do not remove or bypass checks for `off_pin` / `debug_pin` or the low-power service files. Changes must preserve safe shutdown/wakeup behaviour.

6. Developer workflows and useful commands
- Run a single capture locally for debugging:
  - `python3 TakePhoto.py` (run on target Pi; some scripts require root or access to `/dev` devices)
- Control cron for testing scheduling behaviors:
  - `sudo service cron stop` and `sudo service cron start` (scripts include `start_cron()` / `stop_cron()` helpers)
- EEPROM / boot settings (Pi5 wake behavior):
  - `sudo -E rpi-eeprom-config --edit` (see `Scheduler.py` comments)
- Enable low-power timer/service (example files in `scripts/MothPower/`):
  - `sudo cp scripts/MothPower/lowpower.service /etc/systemd/system/` then `sudo systemctl enable --now lowpower.timer` (verify names before enabling)

7. Files to inspect for context when editing
- `TakePhoto.py` — main capture flow and GPIO/mode checks.
- `Scheduler.py` — schedule generation, EEPROM handling, crontab usage, and name generation (uses `wordlist.csv` files).
- `UpdateDisplay.py` and `scripts/RaspberryPi_JetsonNano_Epaper/` — e-paper integration and display formatting.
- `scripts/MothPower/` — low power scripts, systemd units and timers; changes here affect boot/power behavior.
- `crontab_examples/` — review before changing scheduling logic; maintain formatting used by repo.

8. Safety and test guidance for agents
- Never remove hardware safety checks (those that read `off_pin`/`debug_pin`, low-storage checks, or power-management scripts) without explicit justification and tests.
- When adding or changing runtime commands, provide the exact `service` / `systemctl` commands and indicate whether root privileges are required.

9. When to ask the human
- If a change affects systemd units, boot-time behavior, or EEPROM settings, ask the repository owner before committing.
- If external dependencies need to be added (new pip packages or system packages), ask how to update installation docs/packaging.

If anything is unclear or you'd like more detail on one area (e.g., camera calibration flow, low-power lifecycle, or CSV schemas), tell me which section to expand and I'll iterate.
