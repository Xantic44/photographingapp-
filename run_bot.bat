@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating virtual environment in .venv...
  py -m venv .venv
  if errorlevel 1 (
    echo [error] Failed to create virtual environment. Ensure Python is installed and on PATH.
    pause
    exit /b 1
  )
)

echo [setup] Installing/updating dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [error] Dependency install failed.
  pause
  exit /b 1
)

echo [check] Running bot health checks...
".venv\Scripts\python.exe" healthcheck.py
if errorlevel 1 (
  echo [error] Health checks failed. Fix errors above and retry.
  pause
  exit /b 1
)

echo [run] Starting Discord bot...
".venv\Scripts\python.exe" bot.py

endlocal
