# LOG_CSV_ANALYSIS.ps1
#
# PowerShell wrapper for LOG_CSV_ANALYSIS.py
# Simplifies running the analysis with common defaults and optional timestamping
#
# Usage:
#   .\LOG_CSV_ANALYSIS.ps1
#   .\LOG_CSV_ANALYSIS.ps1 -LogFolder "d:\custom\logs" -OutputFile "custom_output.csv"
#   .\LOG_CSV_ANALYSIS.ps1 -Timestamp
#
# Parameters:
#   -LogFolder     Path to folder containing .log files (default: .\data-logs\)
#   -OutputFile    Output CSV filename (default: shutter_time_date.csv)
#   -Timestamp     If specified, appends date to filename (e.g., shutter_time_date_2026-01-29.csv)

param(
    [string]$LogFolder = ".\data-logs\",
    [string]$OutputFile = "shutter_time_date.csv",
    [switch]$Timestamp
)

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Resolve absolute path for log folder
if (-not [System.IO.Path]::IsPathRooted($LogFolder)) {
    $LogFolder = Join-Path $ScriptDir $LogFolder
}

# Add timestamp to output filename if requested
if ($Timestamp) {
    $DateStamp = Get-Date -Format "yyyy-MM-dd"
    $BaseName = [System.IO.Path]::GetFileNameWithoutExtension($OutputFile)
    $Extension = [System.IO.Path]::GetExtension($OutputFile)
    $OutputFile = "${BaseName}_${DateStamp}${Extension}"
}

# Verify Python script exists
$PythonScript = Join-Path $ScriptDir "LOG_CSV_ANALYSIS.py"
if (-not (Test-Path $PythonScript)) {
    Write-Host "Error: LOG_CSV_ANALYSIS.py not found at: $PythonScript" -ForegroundColor Red
    exit 1
}

# Verify log folder exists
if (-not (Test-Path $LogFolder)) {
    Write-Host "Error: Log folder not found at: $LogFolder" -ForegroundColor Red
    exit 1
}

Write-Host "Starting log analysis..." -ForegroundColor Green
Write-Host "  Log folder: $LogFolder"
Write-Host "  Output file: $OutputFile"
Write-Host ""

# Run Python script
python $PythonScript $LogFolder $OutputFile

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Analysis complete!" -ForegroundColor Green
    $OutputPath = Join-Path $LogFolder $OutputFile
    if (Test-Path $OutputPath) {
        $FileSize = (Get-Item $OutputPath).Length / 1KB
        Write-Host "  Output: $OutputPath ($([math]::Round($FileSize, 1)) KB)" -ForegroundColor Green
    }
} else {
    Write-Host ""
    Write-Host "Analysis failed with exit code: $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}
