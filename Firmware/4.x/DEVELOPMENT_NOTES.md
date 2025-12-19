# Mothbox-wintertime Firmware 4.x — Development Notes

## Session Overview
**Date Range:** December 3-19, 2025  
**Focus:** Exposure convergence optimization for Arducam OV64A40 camera on Raspberry Pi 5  
**Current Version:** rpicam-take.py v1.9

---

## Major Issues Addressed

### 1. Wi-Fi Turning Off After Boot
**Problem:** System lost Wi-Fi connectivity ~10 minutes after boot.  
**Root Cause:** `systemd` lowpower.timer was blocking Wi-Fi interface after idle period.  
**Solution:** Added conditional `WIFI_LOWPOWER=False` flag in `controls.txt` to disable automatic Wi-Fi blocking during low-power mode.  
**Status:** ✅ RESOLVED

### 2. Poor Image Focus with --immediate Flag
**Problem:** Images captured with `--immediate` flag were blurry.  
**Root Cause:** ISP (Image Signal Processor) needs ~1.5x wall-clock time for proper demosaicing, sharpening, and tone mapping. `--immediate` skips this.  
**Solution:** Completely removed `--immediate` flag from all capture commands.  
**Status:** ✅ RESOLVED — Sharp images confirmed in production

### 3. Slow Exposure Convergence (4-5 iterations needed)
**Problem:** Convergence to target brightness took too many iterations.  
**Initial Baseline:** 97.1% of captures converged in ≤4 iterations (2025-12-04 data).  
**Goal:** Maintain or improve convergence speed.

---

## Exposure Algorithm Evolution

### Version 1.2 → 1.5: Foundation
- Added `GammaExponent` (default 2.2) to CSV for non-linear exposure correction
- Implemented dynamic gamma: `gamma_dynamic = 1.0 + (gamma - 1.0) × clamp(|error|/threshold, 0, 1)`
- Added overshoot damping: sign-flip detection with 2-iteration settle mode (±0.25 delta limit)
- Added early stops at `MinExposure` (too bright) and `MaxExposure` (too dark)

### Version 1.6: Adaptive Gamma Thresholds
**Problem:** Single `GammaTransitionError=0.10` didn't adapt to different brightness regimes.  
**Solution:** Added three-mode adaptive system:
- **Dark mode** (mean < 150): `GammaTransitionError_Dark=0.08` — sharper correction for underexposed
- **Normal mode** (150-185): `GammaTransitionError_Normal=0.10` — baseline
- **Bright mode** (mean > 185): `GammaTransitionError_Bright=0.06` — gentler correction near ceiling

**Result:** 97.1% convergence in ≤4 iterations, 12.1% overshoot rate (acceptable).

### Version 1.7: Gamma Exponent Testing & Revert
**Test:** Increased `GammaExponent` from 2.2 → 4.5 to reduce iterations.  
**Outcome:** **FAILED** — 43.3% overshoot rate (vs 12.1%), 103% increase in 5-iteration cases.  
**Decision:** Reverted to `GammaExponent=2.2`, kept adaptive system active.

### Version 1.8: Saturated Fast-Drop & Bright Aggressiveness
**Changes:**
1. Added **saturated fast-drop**: When mean ≥ 240, force factor to 1/MaxChangeFactor (0.05) to escape blown-out starts quickly
2. Made bright mode more aggressive:
   - `GammaTransitionError_Bright`: 0.06 → 0.05
   - `GammaBrightThreshold`: 15 → 10 (triggers earlier)

**Result:** 3 iterations to drop from 240s exposure, but post-saturation convergence still slow (15-20 iterations due to gentle 0.84-0.87 factors).

### Version 1.9: Increased Gamma Exponent (Current)
**Problem:** Even with aggressive thresholds, factors in 180-186 brightness range stayed at 0.84-0.87 (too gentle).  
**Analysis:** 
- Error = 170 - 183 = -13
- Scale = |−13/170| / 0.05 = 1.52 → clamps to 1.0
- Gamma stays at full 2.2, giving (170/183)^2.2 ≈ 0.846

**Solution:** Increased `GammaExponent` from 2.2 → 3.0  
**Expected:** (170/185)^3.0 ≈ 0.76, (170/180)^3.5 ≈ 0.73 — should achieve 4-6 iteration convergence.  
**Status:** Pending validation with production data.

---

## Key Configuration Settings (winter_camera.csv)

| Setting | Value | Purpose |
|---------|-------|---------|
| `TargetMean` | 170 | Target brightness (0-255 scale) |
| `TolerancePct` | 5% | Allow ±8.5 brightness units variance |
| `MinExposure` | 100µs | Prevent too-bright captures |
| `MaxExposure` | 240s | Allow long exposures for low light |
| `LoopIterations` | 5 (or 20 for testing) | Max iterations before final capture |
| `MaxChangeFactor` | 20 | Limit per-iteration exposure change to ±20× |
| `GammaExponent` | 3.0 | Non-linear correction (currently tuning) |
| `GammaTransitionError_Dark` | 0.08 | Threshold for dark mode (mean < 150) |
| `GammaTransitionError_Normal` | 0.10 | Threshold for normal mode |
| `GammaTransitionError_Bright` | 0.05 | Threshold for bright mode (mean > 180) |
| `GammaDarkThreshold` | 20 | Brightness units below target to trigger dark |
| `GammaBrightThreshold` | 10 | Brightness units above target to trigger bright |

---

## Production Data Analysis Summary

### 2025-12-04 (V1.7, γ=2.2, adaptive thresholds)
- **Convergence:** 97.1% in ≤4 iterations (33/34 captures)
- **2-iter convergence:** 44.1% (excellent fast path)
- **5-iter cases:** 2.9%
- **Overshoot rate:** 12.1% (acceptable)
- **Status:** Baseline optimal performance

### 2025-12-05 (V1.7, γ=4.5 test)
- **Convergence:** 94.1% in ≤4 iterations (regression from 97.1%)
- **1-iter cases:** 55.9% (false positive — saturation masking)
- **5-iter cases:** 5.9% (103% increase vs γ=2.2)
- **Overshoot rate:** 43.3% (CRITICAL problem)
- **Decision:** Gamma 4.5 too aggressive, reverted immediately

### 2025-12-05 (V1.8, γ=2.2, saturated fast-drop)
- **Test 1 (max exposure start):** 20 iterations to tolerance (saturated fast-drop worked, but post-saturation convergence slow)
- **Test 2 & 3 (near-target starts):** 1 iteration each (excellent when close)
- **Issue:** 0.84-0.87 factors in bright range still inadequate
- **Next step:** Increase gamma to 3.0

---

## Known Issues & Next Steps

### 1. Convergence Speed (V1.9 validation pending)
- **Issue:** Post-saturation convergence requires 15-20 iterations with factors ~0.85
- **Fix Applied:** `GammaExponent` 2.2 → 3.0
- **Action Required:** Run production tests with V1.9 to validate 4-6 iteration target
- **Fallback:** If still slow, consider `GammaExponent=3.5`

### 2. flock Permission Issue (Production)
- **Issue:** Cron job fails with "Permission denied" on `/tmp/rpicam-take.lock`
- **Solution Applied:** Recreate lock file with 666 permissions: `sudo chmod 666 /tmp/rpicam-take.lock`
- **Better Solution:** Pre-create lock in cron before flock call
- **Status:** Need to verify cron is running successfully post-fix

### 3. ISP Variance (Fundamental Limitation)
- **Issue:** ±5-10 brightness unit inherent noise from ISP processing prevents 100% deterministic convergence
- **Impact:** Some captures will always need 5 iterations due to jitter
- **Workaround:** Adaptive thresholds help, but PID control not viable

### 4. Log File Fragmentation
- **Issue:** Production logs stored in two places: `/home/pi/Desktop/Mothbox/winter_scripts/rpicam-take.log` (main) and `/media/pi/USB DISK/winter_images_data/rpicam-take-data.log` (data captures)
- **Action:** Keep both for audit trail; brightness data goes to main log only
- **Status:** Working as designed

---

## Scripts & Files Modified

### Core Capture Script
- **`winter_scripts/rpicam-take.py`** — v1.9
  - Saturated fast-drop (mean ≥ 240)
  - Adaptive gamma thresholds (Dark/Normal/Bright)
  - Dynamic gamma scaling with overshoot damping
  - Early stops at exposure limits
  - Brightness appended to final filenames

### Configuration
- **`winter_scripts/winter_camera.csv`**
  - `GammaExponent` = 3.0 (increased from 2.2)
  - `GammaTransitionError_Bright` = 0.05
  - `GammaBrightThreshold` = 10

### Manual Testing
- **`winter_scripts/data-capture`** — Test harness
  - Runs same cron job manually
  - Supports `--keep-intermediates` flag
  - Logs to external USB storage for validation

### Low-Power Management
- **`scripts/MothPower/lowpower.sh`** — Conditional Wi-Fi blocking
  - `WIFI_LOWPOWER=False` in `controls.txt` disables Wi-Fi shutdown
- **`controls.txt`** — Device controls
  - `WIFI_LOWPOWER=False`

---

## Cron Job Configuration

```bash
*/30 * * * * touch /tmp/rpicam-take.lock 2>/dev/null; /usr/bin/flock -n /tmp/rpicam-take.lock /usr/bin/python3 /home/pi/Desktop/Mothbox/winter_scripts/rpicam-take.py --out-dir "/media/pi/USB DISK/winter_images" >> /home/pi/Desktop/Mothbox/winter_scripts/rpicam-take.log 2>&1
```

**Note:** Pre-create lock file to avoid permission issues on cron startup.

---

## Next Actions (Priority Order)

1. **Validate V1.9 (GammaExponent=3.0)** with production 24-hour run
   - Expected: 4-6 iterations for most captures
   - Target: ≥95% convergence in ≤4 iterations
   - Monitor: data-logs for overshoot rate

2. **Verify cron lock fix** — ensure no "Permission denied" errors in rpicam-take.log

3. **If V1.9 still slow:** Test `GammaExponent=3.5`

4. **If V1.9 overshoots:** Lower `GammaTransitionError_Bright` to 0.04 or increase `GammaBrightThreshold` back to 12

5. **Optimize LoopIterations** — once convergence validated, reduce from 5 back to 3-4 to save time on near-target starts

---

## Design Philosophy

The exposure convergence system uses **dynamic gamma scaling** as the core mechanism:

1. **Normalized error** tells us how far from target (as a fraction of target)
2. **Gamma exponent** (currently 3.0) controls aggressiveness of correction
3. **Adaptive thresholds** (Dark/Normal/Bright) customize behavior per brightness region
4. **Saturation fast-drop** (mean ≥ 240) escapes blown-out starts quickly
5. **Overshoot damping** (sign-flip detection) prevents oscillation
6. **Early stops** (min/max exposure) prevent futile cycling

This avoids PID control (which struggles with ISP jitter) and provides **predictable, bounded convergence** even with system noise.

---

## Resources & References

- **Arducam OV64A40 Datasheet:** 64MP fixed-focus, CSI-2 interface
- **libcamera/rpicam-still:** Linux camera framework used on Raspberry Pi 5
- **Raspberry Pi 5 Camera Module:** Dual CSI connectors, PiSP ISP processor
- **systemd timers:** Used for low-power scheduling (lowpower.timer)

---

**Last Updated:** 2025-12-19  
**Current Status:** V1.9 deployed, awaiting production validation
