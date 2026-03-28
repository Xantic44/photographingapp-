@echo off
setlocal

REM Always run from the app folder so relative paths work.
set "APP_DIR=C:\Users\Diar_\Desktop\pythonprojects\photo_social_app"
cd /d "%APP_DIR%"

REM Pick interpreter in this order:
REM 1) project venv (no manual activation needed)
REM 2) global python on PATH
REM 3) py launcher on PATH
set "PY_EXE="

if exist ".venv\Scripts\python.exe" (
  set "PY_EXE=.venv\Scripts\python.exe"
) else (
  where python >nul 2>&1
  if not errorlevel 1 (
    set "PY_EXE=python"
  ) else (
    where py >nul 2>&1
    if not errorlevel 1 (
      set "PY_EXE=py"
    )
  )
)

if "%PY_EXE%"=="" (
  echo [error] No Python interpreter found.
  echo Install Python globally or create .venv in this folder.
  exit /b 1
)

REM Start Flask app.
"%PY_EXE%" app.py

endlocal
