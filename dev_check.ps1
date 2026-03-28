$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv/Scripts/python.exe")) {
    throw ".venv is missing. Run run_bot.ps1 or run_bot.bat once to set up the environment."
}

Write-Host "[check] Running healthcheck.py..."
& ".venv/Scripts/python.exe" "healthcheck.py"
if ($LASTEXITCODE -ne 0) {
    throw "healthcheck.py failed."
}

Write-Host "[check] Running smoke_check.py..."
& ".venv/Scripts/python.exe" "smoke_check.py"
if ($LASTEXITCODE -ne 0) {
    throw "smoke_check.py failed."
}

Write-Host "[ok] Dev checks passed."
