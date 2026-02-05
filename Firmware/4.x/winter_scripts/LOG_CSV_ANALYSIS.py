#!/usr/bin/env python3
"""
LOG_CSV_ANALYSIS.py

Purpose: Extract shutter times from rpicam-take.py log files and generate a CSV
organized by date and half-hourly time slot.

Usage:
  python LOG_CSV_ANALYSIS.py <log_folder> <output_filename>

Example:
  python LOG_CSV_ANALYSIS.py "d:\\path\\to\\data-logs" "shutter_time_date.csv"

Output:
  CSV file with:
  - Rows: 48 half-hourly time slots (00:00, 00:30, 01:00, ..., 23:30)
           Only includes slots that have at least one capture across all dates
  - Columns: Dates (chronologically ordered, YYYY-MM-DD format)
  - Values: Shutter times in microseconds, or "N/A" for missing captures

Logic:
  1. Scans all .log files in the specified folder
  2. For each "YYYY-MM-DD-HH-MM-SS iter1" timestamp line:
     - Searches forward for the next "Capture complete. Final exposure (us):" line
     - Extracts the shutter value from that line
     - Associates this shutter value with the timestamp (represents next capture start)
     - Rounds timestamp down to nearest half-hour slot (00:00 or 00:30, etc.)
  3. Collects all dates and time slots across all log files
  4. Generates CSV with:
     - Header row: Time, then all dates chronologically
     - Data rows: One per time slot with shutter values
     - Only includes time slots that have captures on at least one date

Error Handling:
  - Logs errors for individual files but continues processing others
  - Reports summary of dates and time slots found
  - Verifies file creation and reports final size
"""

import os
import re
import csv
import sys
from collections import defaultdict


def parse_log_files(log_folder):
    """
    Parse all .log files in folder and extract shutter data.
    
    Returns: {date_str: {time_slot: shutter_us}}
    """
    data_by_date = defaultdict(dict)
    log_files = [f for f in os.listdir(log_folder) if f.endswith('.log')]
    
    print(f"Processing {len(log_files)} log files from: {log_folder}\n")
    
    for log_file in log_files:
        file_path = os.path.join(log_folder, log_file)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            i = 0
            while i < len(lines):
                line = lines[i]
                
                # Match timestamp at start of line followed by "iter"
                # Pattern: YYYY-MM-DD-HH-MM-SS iter1 (or iter2, iter3, etc.)
                ts_match = re.match(r'(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})\s+iter', line)
                
                if ts_match:
                    # Found a capture start timestamp
                    capture_start_ts = ts_match.group(0)[:19]  # Extract YYYY-MM-DD-HH-MM-SS
                    
                    # Search forward to find corresponding "Capture complete" line
                    j = i + 1
                    capture_complete_exposure = None
                    
                    while j < len(lines):
                        if 'Capture complete. Final exposure (us):' in lines[j]:
                            exposure_match = re.search(
                                r'Capture complete\. Final exposure \(us\): (\d+)',
                                lines[j]
                            )
                            if exposure_match:
                                capture_complete_exposure = exposure_match.group(1)
                            break
                        j += 1
                    
                    if capture_complete_exposure:
                        # Parse timestamp
                        date_part = capture_start_ts[:10]  # YYYY-MM-DD
                        hour = int(capture_start_ts[11:13])
                        minute = int(capture_start_ts[14:16])
                        
                        # Round down to nearest half-hour slot
                        if minute < 30:
                            time_slot = f"{hour:02d}:00"
                        else:
                            time_slot = f"{hour:02d}:30"
                        
                        # Store shutter time for this date and time slot
                        data_by_date[date_part][time_slot] = capture_complete_exposure
                
                i += 1
        
        except Exception as e:
            print(f"  Error reading {log_file}: {e}")
    
    return data_by_date


def generate_csv(data_by_date, output_path):
    """
    Generate CSV file from parsed shutter data.
    
    CSV structure:
    - Header: Time, then all dates chronologically
    - Rows: One per half-hourly time slot
    - Values: Shutter times in microseconds, or "N/A" for missing data
    """
    # Collect all unique dates and time slots
    all_dates = sorted(data_by_date.keys())
    all_time_slots = sorted(set(
        slot for date_data in data_by_date.values()
        for slot in date_data.keys()
    ))
    
    print(f"Summary:")
    print(f"  Total dates: {len(all_dates)}")
    print(f"  Total time slots with captures: {len(all_time_slots)}")
    print(f"  CSV dimensions: {len(all_time_slots)} rows x {len(all_dates) + 1} columns")
    print(f"\nDate range: {all_dates[0]} to {all_dates[-1]}")
    print(f"Time slots (sample): {all_time_slots[:5]} ... {all_time_slots[-5:]}\n")
    
    # Generate CSV
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Header row
        header = ['Time'] + all_dates
        writer.writerow(header)
        
        # Data rows: one per time slot, chronologically ordered
        for time_slot in all_time_slots:
            row = [time_slot]
            for date in all_dates:
                value = data_by_date[date].get(time_slot, 'N/A')
                row.append(value)
            writer.writerow(row)
    
    file_size_kb = os.path.getsize(output_path) / 1024
    print(f"CSV file created: {output_path}")
    print(f"File size: {file_size_kb:.1f} KB")


def main():
    """Main entry point."""
    if len(sys.argv) != 3:
        print("Usage: python LOG_CSV_ANALYSIS.py <log_folder> <output_filename>")
        print("\nExample:")
        print('  python LOG_CSV_ANALYSIS.py "d:\\path\\to\\data-logs" "shutter_time_date.csv"')
        sys.exit(1)
    
    log_folder = sys.argv[1]
    output_filename = sys.argv[2]
    
    # Validate log folder
    if not os.path.isdir(log_folder):
        print(f"Error: Log folder not found: {log_folder}")
        sys.exit(1)
    
    # Determine output path
    output_path = os.path.join(log_folder, output_filename)
    
    # Parse logs
    data_by_date = parse_log_files(log_folder)
    
    if not data_by_date:
        print("Error: No data found in log files. Check folder and file format.")
        sys.exit(1)
    
    # Generate CSV
    generate_csv(data_by_date, output_path)
    print("\nDone!")


if __name__ == '__main__':
    main()
