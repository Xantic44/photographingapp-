@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [error] .venv is missing. Run run_bot.bat once to set up the environment.
  exit /b 1
)

echo [check] Running healthcheck.py...
".venv\Scripts\python.exe" healthcheck.py
if errorlevel 1 (
  echo [error] healthcheck.py failed.
  exit /b 1
)

echo [check] Running smoke_check.py...
".venv\Scripts\python.exe" smoke_check.py
if errorlevel 1 (
  echo [error] smoke_check.py failed.
  exit /b 1
)

echo [ok] Dev checks passed.
endlocal
