$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv/Scripts/python.exe")) {
    Write-Host "[setup] Creating virtual environment in .venv..."
    py -m venv .venv
}

Write-Host "[setup] Installing/updating dependencies..."
& ".venv/Scripts/python.exe" -m pip install --upgrade pip
& ".venv/Scripts/python.exe" -m pip install -r requirements.txt

Write-Host "[check] Running bot health checks..."
& ".venv/Scripts/python.exe" "healthcheck.py"
if ($LASTEXITCODE -ne 0) {
    throw "Health checks failed. Fix errors above and retry."
}

Write-Host "[run] Starting Discord bot..."
& ".venv/Scripts/python.exe" "bot.py"
