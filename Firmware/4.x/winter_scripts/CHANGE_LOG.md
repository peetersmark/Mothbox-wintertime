# Mothbox Winter Camera Project — Change Log

## Summary
Chronological record of all work, goals, and functionality added to the Mothbox winter camera system, from initial project setup through production exposure loop implementation and bug fixes.

---

## 1. Project Initialization and Architecture Scan
**Goal:** Establish new development framework (`winter_scripts`) for extended camera functionality, learn existing codebase patterns, and define hardware assumptions.

**Details:**
- Decided to create parallel scripts folder (`winter_scripts`) rather than modify existing repository code
- Scanned Scheduler.py, TakePhoto.py, UpdateDisplay.py, and MothPower to extract GPIO pin usage, CSV field conventions, and system commands
- Extracted hardware specifics: OFF pin (GPIO 16), DEBUG pin (GPIO 12), CSV `SETTING,VALUE,DETAILS` format, exposure time storage patterns

**Functionality Added:**
- Created `winter_scripts/` folder structure with README, `config_loader.py`, `gpio_safe.py`, `sample_capture.py`, `requirements.txt`
- Defined simplified assumptions: Raspberry Pi 5 only, Arducam 64MP OV64A40 camera, no relay/lights usage (`USE_LIGHTS=False`)
- Created `defaults.py` with project-wide hardware constants

**Chat Log References:** Lines 1–200

---

## 2. Diagnostic Script: rpicam-test.py
**Goal:** Create manual camera testing tool to diagnose exposure, gain, and AWB behavior across wide exposure ranges (1/100s to 1000s) with manual EV control (-16 to +16).

**Details:**
- Initial attempt used picamera2 library, but errors indicated libcamera/rpicam-still should be used instead
- Shifted approach: implemented rpicam-test.py using only `rpicam-still` CLI tool
- Added datetime stamps to filenames (format: `yyyy-mm-dd-hh-mm-ss`)
- Explored EXIF metadata discrepancies: filename vs actual exposure, EXIF rounding, auto-gain/AWB interference

**Functionality Added:**
- `rpicam-test.py`: Manual exposure testing with configurable shutter (µs) and EV (-16 to +16)
- Captures at 9248×6944 (full resolution)
- Writes metadata to stdout for inspection
- Filename format: `rpicam_YYYY-MM-DD-HH-MM-SS_exNNNNNNNus_evNN.jpg`

**Technical Findings:**
- EXIF exposure time may differ from requested (rounding to rationals, driver interpretation varies)
- Image brightness is not purely `ExposureTime`; depends on analogue gain, digital gain, tone-mapping (gamma), AWB
- Auto-gain/auto-exposure can change brightness even with fixed shutter if not explicitly locked

**Chat Log References:** Lines 289–460

---

## 3. Enhanced Diagnostic Script: rpicam-test2.py
**Goal:** Create structured diagnostic tool with CSV manifest, locked auto-settings, and calculated mean brightness for systematic exposure/gain characterization.

**Details:**
- Added CSV manifest output to log all captures with metadata, requested values, and calculated mean brightness
- Implemented auto-settings locking: fixed `--analoggain`, `--awbgains` to isolate exposure as sole variable
- Kept JPEG output (no raw captures)
- Investigated EV metadata field availability and correlation with exposure changes

**Functionality Added:**
- `rpicam-test2.py`: Systematic capture loop with CSV manifest
- CSV columns: timestamp, exposure_us (requested), shutter_actual (from metadata), mean_brightness (PIL), all metadata fields
- Fixed gain + fixed AWB to isolate exposure linearity testing
- Support for testing exposure ranges with locked AE/AWB

**Technical Details:**
- Query: Does metadata contain EV field? Answer: not always; implementations vary
- EV impact: EV typically affects auto-exposure. With fixed gain+shutter, EV may be ignored
- Effective exposure = shutter_time × analogue_gain × digital_gain (visible in EXIF)
- Brightness non-linearity: JPEG tone-mapping compresses highlights; linear sensor exposure ≠ visible JPEG brightness

**Chat Log References:** Lines 540–695

---

## 4. Production Capture Script: rpicam-take.py (v1.0 - 2025-12-XX)
**Goal:** Implement automatic exposure convergence to target brightness using multiplicative proportional feedback loop.

**Details:**
- Reads camera settings from `winter_camera.csv` (SETTING,VALUE,DETAILS format)
- Iterative exposure adjustment: captures image → measures mean brightness → calculates factor toward target → clamps by MinExposure/MaxExposure and per-iteration MaxChangeFactor
- Early stops: within tolerance, at MinExposure (still bright), at LoopIterations limit
- Respects GPIO OFF (16) and DEBUG (12) pins for safe shutdown and verbosity
- Writes manifest CSV per capture session with all metadata and iteration details
- Updates `winter_camera.csv` ExposureTime field with final exposure used

**Features:**
- Exposure loop: multiplicative proportional control with configurable target mean (0–255), tolerance (%), min/max exposure, and per-iteration change limits
- CSV-driven configuration: `TargetMean`, `LoopIterations`, `TolerancePct`, `MinExposure`, `MaxExposure`, `MaxChangeFactor`
- Manifest logging: timestamp, iteration count, exposure, measured mean, all EXIF metadata, retry status
- Retry logic: up to 2 attempts on rpicam-still failure
- GPIO safety: aborts if OFF pin active, verbose logging if DEBUG pin active
- Dry-run mode: prints all commands without capturing
- Keep-intermediates option: retain iter1, iter2, ... images or delete and keep only final

**Technical Implementation:**
- Calculation: `new_exposure = current_exposure × (target_mean / current_mean)` with safety clamping
- Safety caps: per-iteration change limited (×MaxChangeFactor, ÷MaxChangeFactor)
- Import shim: adds `winter_scripts/` to sys.path so local modules (`gpio_safe.py`, `config_loader.py`) import correctly from any working directory
- Dependency note: requires Pillow for mean brightness calculation from JPEG

**CSV Template (winter_camera.csv):**
```
SETTING,VALUE,DETAILS
ExposureTime,1000,Last used exposure time in microseconds
AnalogueGain,,Optional fixed analogue gain
Gain,,Optional fixed overall gain
AwbGains,,Optional fixed awb gains as R,G
Width,9248,Default capture width (px)
Height,6944,Default capture height (px)
TargetMean,170,Target mean brightness (0–255)
LoopIterations,5,Number of iterations for exposure loop
RetryCount,2,Number of rpicam-still retries on failure
MinExposure,100,Minimum exposure in microseconds
MaxExposure,240000000,Maximum exposure in microseconds (240s)
TolerancePct,5,Stop loop when within this percent of target
MaxChangeFactor,20,Maximum multiplicative change per iteration
```

**Chat Log References:** Lines 697–1100 (design questions), Lines 1100–1200 (implementation)

---

## 5. Bug Investigation: Long Exposure Logging and Performance
**Goal:** Analyze production log data to identify system behavior, timing overhead, white balance variations, and efficiency of convergence algorithm.

**Details:**
- Analyzed 2025-12-03 production logs from multi-day test run
- Events studied: 140 total captures, distribution across 1–5 iterations, early-stop patterns
- Key event: 2026-01-07-18-00-01 capture hitting MaxExposure with stale brightness check
- Key event: 2026-01-07-18-30-01 capture showing duplicate redundant final captures
- Timing analysis: long exposures (240s) taking ~12 minutes wall-clock (240s exposure + 240s overhead + duplicate final)
- White balance shifts observed during dawn/dusk transitions (warm ↔ cool color temperature swings)

**Findings:**
- **Iteration efficiency:** 39.3% converge in 1 iter, 25.7% in 2 iters, 18.6% need max 5 iters
- **Early stops working:** MinExposure: 1 case, MaxExposure: 1 case, Reuse within tolerance: 114 cases (81% success)
- **5-iteration failures:** 26 captures (18.6%) didn't converge within tolerance; pattern shows "creeping convergence" stuck just outside tolerance window
- **MaxExposure issue:** System breaks loop before testing, final capture often over/underexposed; reuse flag not set, causing duplicate final captures

**Chart Log References:** Lines 2800–3500 (log analysis), Lines 3500–4700 (white balance investigation)

---

## 6. Bug #1 and Bug #2: MaxExposure Early-Stop Logic
**Goal:** Identify and document issues with MaxExposure early-stop code that uses stale brightness data and doesn't reuse images properly.

**Details:**

**Bug #1:** MaxExposure early-stop uses stale brightness value
- Location: rpicam-take.py lines 397–401
- Issue: Breaks loop when `current_exposure >= max_exposure AND mean_b < target_mean`, but `mean_b` is from *previous* (lower) exposure
- Example: Iter2 at 17.67s gets mean=68.82 (dark) → calculates new_exposure=266s → caps to 240s → checks old mean against max → breaks → final capture at 240s produces mean=201.87 (overexposed, outside tolerance)
- Impact: Contradictory messaging ("without achieving target brightness" but final image is bright)

**Bug #2:** MaxExposure early-stop doesn't set reuse flag
- Location: rpicam-take.py lines 397–401 (same block)
- Issue: Breaks without setting `reuse_final=True` and related variables, causing redundant final capture at same exposure
- Example: Iter1 at 240s gets mean=155.37 (below target) → stops → takes ANOTHER 240s final → mean=157.09 (still below target)
- Impact: Doubles runtime at MaxExposure (~12 minutes instead of ~4–5 minutes); wastes power/battery; creates near-identical duplicate images

**Both bugs stem from:**
- Early-stop logic breaks immediately when MaxExposure is reached, without ensuring the reuse mechanism is properly triggered
- Mixing check timing (using previous iteration's brightness to decide about current iteration)

**Chat Log References:** Lines 4726–5100 (bug discovery and analysis)

---

## 7. Solution Design: Combined MaxExposure Fix (v2.0 Design)
**Goal:** Design fix for Bugs #1 and #2 that allows one accurate test at MaxExposure, then properly reuses if convergence impossible.

**Solution Approach:**
- Add `prev_was_at_max` tracking variable (lines 257)
- Remove immediate early-stop; instead:
  1. First time hitting MaxExposure: let loop continue to get actual brightness at MaxExposure
  2. Second time at MaxExposure: if still below target, set reuse flag and break
  3. This ensures one measurement at MaxExposure before stopping
- Sets all reuse variables (`reuse_final`, `reused_file`, `reused_metadata`, `reused_mean`, `reuse_iteration_stage`) correctly

**Expected Outcome:**
- Bug #1 fixed: Uses actual brightness at MaxExposure, not stale value
- Bug #2 fixed: Reuse logic properly triggered, no redundant final captures
- Performance: ~4–5 min per MaxExposure event (vs. ~12 min currently)
- Consistency: MaxExposure early-stop now behaves like MinExposure early-stop and tolerance checks

**Chat Log References:** Lines 5100–5200 (discussion of options), Lines 5200–5300 (design finalization)

---

## 8. Implementation: rpicam-take.py v2.0 (2026-01-20)
**Goal:** Apply combined MaxExposure fix to production script.

**Changes Applied:**
- **Line 24–26:** Updated version header to v2.0, date 2026-01-20
- **Line 257:** Added `prev_was_at_max = False` tracking variable
- **Lines 397–414:** Replaced problematic early-stop with new logic:
  - Check if previous iteration was at MaxExposure AND current is still at MaxExposure AND still below target
  - If true: set all reuse variables and break (reuse the iteration image)
  - Track `prev_was_at_max` state for next iteration
  - This ensures one test at MaxExposure before stopping with reuse properly activated

**Version Update:**
```
Version: 2.0 - 2026-01-20
Changes: Fixed MaxExposure early-stop logic (Bug #1, #2): now tests MaxExposure once to get accurate brightness,
         then reuses that iteration if still below target. Eliminates redundant final captures and stale brightness checks.
```

**Testing Plan:**
- Monitor production logs for MaxExposure events
- Verify no duplicate final captures in logs
- Confirm final brightness values are accurate
- Measure runtime improvement (~50% faster for MaxExposure events)

**Chat Log References:** Lines 5200–5387 (display of changes), Lines 5350–5387 (application and version update)

---

## Appendix: Key Technical Insights

### Exposure and Brightness
- Linear sensor exposure (time × gain) does NOT linearly map to JPEG brightness
- JPEG processing includes: tone-mapping (gamma), white balance, denoise, saturation adjustments
- Multiplicative proportional control works well for sensor-level parameters but must account for nonlinear processing

### Auto-Exposure and Gain
- rpicam-still does not expose AeEnable flag directly
- Fixing gain + shutter together with `--ev 0` reduces AE interference
- Fixed `--analoggain` and `--awbgains` are needed to test brightness linearity

### CSV and Configuration Patterns
- Repository uses `SETTING,VALUE,DETAILS` format (three-column CSV)
- Exposure times stored in microseconds (integers) for precision
- CSV modified in-place to persist state (e.g., `ExposureTime` updated each run)

### GPIO Safety
- OFF pin (GPIO 16, BCM): signal to shut down immediately
- DEBUG pin (GPIO 12, BCM): enable verbose logging
- These pins are read at startup; OFF triggers early abort

### Iteration Control
- Early stops: (1) within tolerance, (2) at MinExposure (still bright), (3) at LoopIterations limit
- Safety cap per iteration: multiplicative change clamped (×MaxChangeFactor, ÷MaxChangeFactor)
- Each iteration captures a new image, measures brightness, calculates new exposure

---

**Generated:** 2026-01-21 from [chat-apste-2026-01-20.md](chat-apste-2026-01-20.md)

## gains and white balance

**Date/Context:** Analysis of 2026-01-26 manifest (`2026-01-26-rpicam_take_manifest.csv`) for rpicam-take v2.1 (2026-01-21). CSV left blank for AnalogueGain/Gain/AwbGains, so camera runs full auto for gains and AWB.

### Automatic control behavior (by time)
- Day (12:30–15:30): shutter 0.3–1.0 ms; analog gain 2.2–5.4×; digital gain ~1.28×; total gain ~2.8–6.9×; AWB ~2.08R/1.27B; color temp ~6,300–6,500K.
- Dusk (16:31–18:01): shutter 0.9–221 ms; analog gain pegged at 8.0×; digital gain 1.38–2.45×; total gain up to 19.6×; AWB warms (2.39R/1.12B); color temp peaks ~6,800–7,900K.
- Night (18:36+): shutter 13–66 s; analog gain 1.0×; digital gain 1.0×; total gain 1.0×; AWB cools (≈1.45R/1.9B); color temp ~3,500–3,800K.

### Why blank gain fields log as “missing”
- `read_camera_csv` converts empty VALUE cells to `None`, so the script logs “Using defaults for missing CSV keys: AnalogueGain, AwbGains, Gain” to note it is using automatic control. This is expected and keeps AE/AWB enabled.

### If you want shorter night shutters
- Forcing high gain helps shorten shutters linearly: 8× analog → 8× shorter shutter (e.g., 66 s → ~8.25 s), but increases noise and reduces dynamic range.
- Tradeoffs:
  - Low gain + long exposure: clean, high dynamic range, but motion blur/star trails and higher wall-clock/power.
  - High gain + short exposure: noisier (shadow/color noise, banding), lower dynamic range/saturation, but freezes motion and reduces power/time.
- Suggested compromise: cap analog gain to 2–4× at night to cut shutters to ~7–15 s with moderate noise; avoid pegging at 8× unless motion/power constraints dominate.
- If implementing logic: consider “if computed shutter > threshold (e.g., 20 s), force analog gain to 2–4×; otherwise leave auto.” This would require code changes to rpicam-take.py (exposure loop) plus a version header bump.

## 9. rpicam-take.py v2.2 (2026-01-26)
- Set fixed daylight AWB gains (AwbGains="2.08,1.27") in winter_camera.csv so captures use a locked daylight white balance instead of auto.
- Updated rpicam-take.py header to Version 2.2 - 2026-01-26 reflecting the AWB lock change.

## 10. rpicam-take.py v2.3 (2026-01-28)
**Goal:** Reduce nighttime shutter times and adjust white balance to cooler temperature.

**Changes Applied:**

### AnalogueGain=3.0 Fixed Gain Setting
- 2026-01-28 testing of v2.2 with locked daylight AWB (2.08R/1.27B @ 6115K) revealed:
  - AWB lock IS functioning correctly—all night captures use requested 2.08R/1.27B gains
  - Night photos appear warm/yellow/orange because locked daylight AWB (6115K) is warmer than auto night AWB (1.45R/1.9B @ 3500K)
  - Current night shutters: 25.5s to 118.7s at AnalogueGain=1.0 (auto)

- Set AnalogueGain=3.0 in winter_camera.csv to lock analog gain at 3×
- Expected effects:
  - Reduce night shutters by ~3×: 25.5s → ~8.5s, 104s → ~35s
  - Moderate noise increase: ~1.7× noise (acceptable tradeoff)
  - Faster exposure convergence during twilight transitions

### AwbGains="1.83,1.52" (5000K White Balance)
- Changed from 6115K daylight (2.08R/1.27B) to estimated 5000K (1.83R/1.52B)
- Calculation: Linear interpolation between observed 3500K (1.45R/1.9B) and 6115K (2.08R/1.27B)
- Goal: Reduce warm/yellow/orange night tint by using cooler white balance setting
- Note: 5000K gains are estimated; may require field testing/adjustment

**Version Update:**
- rpicam-take.py header updated to Version 2.3 - 2026-01-28

**Chat Log References:** 2026-01-28 session

## 11. rpicam-take.py v2.4 (2026-01-28)
**Goal:** Revert AnalogueGain after daytime overexposure testing.

**Problem Identified:**
- v2.3 field testing on 2026-01-28 showed severe daytime overexposure
- Daytime captures (10:30-13:00) showed mean brightness 230-236 vs. target 170
- Root cause: AnalogueGain=3.0 fixed too high for bright daylight
- Script hit MinExposure=100us floor but still overexposed with AG=3.0
- Cannot compensate further without hardware minimum shutter faster than 100us

**Changes Applied:**
- Reverted AnalogueGain to blank (automatic) in winter_camera.csv
- Kept AwbGains="1.83,1.52" (5000K white balance) from v2.3
- Updated rpicam-take.py to Version 2.4 - 2026-01-28

**Outcome:**
- Automatic gain control restored for daytime exposure management
- Night captures will return to longer shutters (13-66s range) but with proper daytime exposure
- 5000K AWB retained to continue testing cooler color temperature

**Lesson Learned:**
- Fixed analog gain requires hardware minimum shutter capability below current 100us limit
- Dynamic gain control needed: high gain only at night, low/auto gain during day
- Future consideration: implement conditional gain logic based on time of day or ambient light

**Chat Log References:** 2026-01-28 session

---

## Section 12: v2.5 — Auto White Balance Restoration (2026-01-29)

**Issue:** Field review of v2.4 photos (5000K AWB) showed insufficient color balance across day/night transition.

**Solution:** Reverted AwbGains to automatic/blank to restore libcamera auto-AWB algorithm.

**Files Changed:** winter_camera.csv (AwbGains blanked), rpicam-take.py header (v2.4 to v2.5)

**Status:** Ready for field testing with auto-AWB.

**Expected Behavior:** libcamera will adjust white balance automatically based on scene lighting conditions.
