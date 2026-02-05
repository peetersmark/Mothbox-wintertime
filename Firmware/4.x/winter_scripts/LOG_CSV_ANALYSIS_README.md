# Log to CSV Analysis — Reusable Shutter Time Extraction

## Overview

`LOG_CSV_ANALYSIS` is a toolset to extract shutter time data from rpicam-take.py log files and generate analysis-ready CSV files. Use it to track exposure patterns over time and identify capture issues.

## Files

- **LOG_CSV_ANALYSIS.py** — Core Python script (cross-platform)
- **LOG_CSV_ANALYSIS.ps1** — PowerShell wrapper for Windows (optional convenience)
- **LOG_CSV_ANALYSIS_README.md** — This file

## Quick Start

### Option 1: Python (Any OS)

```bash
python LOG_CSV_ANALYSIS.py "d:\path\to\data-logs" "shutter_time_date.csv"
```

### Option 2: PowerShell (Windows)

```powershell
.\LOG_CSV_ANALYSIS.ps1
# Or with custom paths:
.\LOG_CSV_ANALYSIS.ps1 -LogFolder "d:\custom\logs" -OutputFile "my_output.csv"
# Or with automatic timestamping:
.\LOG_CSV_ANALYSIS.ps1 -Timestamp
```

## CSV Output Format

### Structure
- **Rows:** 48 half-hourly time slots (00:00, 00:30, 01:00, ..., 23:30)
  - Only includes time slots with at least one capture across all dates
- **Columns:** Time slot (first column) + one column per date (chronologically ordered)
- **Values:** Shutter time in microseconds, or "N/A" for missing captures

### Example
```
Time,2025-12-16,2025-12-17,2025-12-18
00:00,37087334,117094501,240000000
00:30,37087334,125920025,240000000
01:00,N/A,N/A,240000000
...
```

## Analysis Logic

The script performs these steps:

1. **Scans log files:** Finds all `.log` files in the specified folder

2. **Matches captures:** For each line starting with a timestamp and "iter":
   - `YYYY-MM-DD-HH-MM-SS iter1 exposure_us=...` — Marks the START of a capture
   - Searches forward for: `Capture complete. Final exposure (us): XXXXX`
   - Associates shutter value with the START timestamp

3. **Maps to half-hours:** Rounds down each timestamp to nearest half-hour:
   - `00:15:32` → `00:00`
   - `00:37:15` → `00:30`
   - `12:58:42` → `12:30`

4. **Generates CSV:** Rows = unique time slots; Columns = all dates; Values = shutter times

## Interpretation

### Identifying Missed Captures
- **Many "N/A" entries** → Captures missed or runtime exceeded cron window
- **Consistent N/A blocks** (e.g., midnight to 06:00) → Expected behavior or scheduling gap

### Shutter Time Patterns
- **Daytime (06:00-18:00):** Typically 1,000-10,000 microseconds (short)
- **Dusk (18:00-20:00):** Ramping up, 10,000-100,000+ microseconds
- **Nighttime (20:00-06:00):** Typically 50,000,000-240,000,000 microseconds (long)
- **240,000,000 (240s):** Hit hardware maximum exposure limit

### Exposure Control Issues
- **Jumps between captures:** May indicate unstable convergence or lighting changes
- **Stuck at 240M (240s):** Subject is very dark; may need higher gain or AwbGains adjustment
- **Stuck at 100-1000:** Subject is very bright; exposure loop may need tuning

## Examples

### Run once with default paths
```bash
cd d:\mark_igloo\mark\Documents\GitHub\Mothbox-wintertime\Firmware\4.x\winter_scripts
python LOG_CSV_ANALYSIS.py ".\data-logs" "shutter_time_date.csv"
```

### Generate timestamped versions (PowerShell)
```powershell
cd d:\mark_igloo\mark\Documents\GitHub\Mothbox-wintertime\Firmware\4.x\winter_scripts
.\LOG_CSV_ANALYSIS.ps1 -Timestamp
# Creates: shutter_time_date_2026-01-29.csv, shutter_time_date_2026-01-30.csv, etc.
```

### Re-analyze old logs (keeping new ones separate)
```bash
python LOG_CSV_ANALYSIS.py "d:\old_logs" "old_shutter_analysis.csv"
python LOG_CSV_ANALYSIS.py "d:\new_logs" "new_shutter_analysis.csv"
```

## Troubleshooting

### No data found / Error
- **Check:** Do .log files exist in the folder?
- **Check:** Are they actual rpicam-take.py logs with "Capture complete" lines?
- **Try:** Inspect first few lines of a log file to verify format

### CSV is empty or has only "N/A"
- **Reason:** No captures recorded in time period
- **Check:** Review log file manually for errors or aborts

### Python not found (Windows)
- **Solution 1:** Use full path: `C:\Python311\python.exe LOG_CSV_ANALYSIS.py ...`
- **Solution 2:** Ensure Python is in PATH: `python --version` should work
- **Solution 3:** Use PowerShell wrapper instead: `.\LOG_CSV_ANALYSIS.ps1`

### Permission denied (PowerShell)
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\LOG_CSV_ANALYSIS.ps1
```

## Technical Notes

### Capture Flow in Logs
Each capture produces multiple log lines:
```
2025-12-17-00-30-01 iter1 exposure_us=117094501 mean=158.72 returncode=0
2025-12-17-00-30-01 iter1 factor=1.173 new_exposure=137371636
2025-12-17-00-36-06 iter2 exposure_us=137371636 mean=181.39 returncode=0
...
Capture complete. Final exposure (us): 125920025
```

- **Start:** First timestamp (00:30:01) — when THIS capture began
- **Final exposure:** 125920025 — the shutter value that WAS USED for THIS capture
- **Next start:** Next timestamp in log — represents next capture's start (maps to 125920025)

### Why timestamps round down?
The log timestamp marks when a capture **starts**. To match it with the shutter value it **produces**, we round down to the nearest half-hour and assume continuous operation within that window.

## Performance

- **15 log files (2-600 KB each):** < 1 second
- **100+ log files:** < 5 seconds
- **Output size:** Typically 10-20 KB (CSV)

## Future Enhancements

Potential additions:
- **Column:** Add "mean brightness" alongside shutter
- **Pivot:** Time slots as rows, dates as columns (current) vs. vice versa
- **Filter:** Include only specific date ranges or time windows
- **Aggregation:** Compute min/max/average shutter per time slot
- **Visualization:** Generate plots or heatmaps from CSV data

## Questions or Issues?

Check the inline comments in `LOG_CSV_ANALYSIS.py` for implementation details.
