@echo off
:: ==============================================================
:: Clerasense – Run Development Server (Windows)
:: ==============================================================
:: Starts the Flask backend which also serves the frontend.
::
:: Prerequisites:
::   1. Run  scripts\setup.bat      (creates venv, installs deps)
::   2. Configure .env              (DATABASE_URL, OPENAI_API_KEY, etc.)
::   3. Run  scripts\setup_db.bat   (initialize database)
::
:: Usage: double-click or run  scripts\run.bat
:: ==============================================================

setlocal enabledelayedexpansion

cd /d "%~dp0\.."
set "PROJECT_ROOT=%cd%"

echo ============================================
echo   Clerasense – Starting Server
echo ============================================
echo.

:: ---- Check .env ----
if not exist ".env" (
    echo ERROR: .env file not found.
    echo        Create .env with your configuration. See README.md.
    pause
    exit /b 1
)

:: ---- Activate virtual environment ----
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo ==> Virtual environment activated.
) else (
    echo WARNING: No virtual environment found at venv\
    echo          Run scripts\setup.bat first, or dependencies may be missing.
)
echo.

echo ==> Starting Clerasense backend (Flask dev server)...
echo     API:      http://127.0.0.1:5000/api/health
echo     Frontend: http://127.0.0.1:5000/
echo.
echo     Press Ctrl+C to stop the server.
echo.

cd backend
python wsgi.py
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Server exited with an error.
    pause
    exit /b 1
)

pause
