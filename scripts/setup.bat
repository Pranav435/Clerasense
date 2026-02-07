@echo off
:: ==============================================================
:: Clerasense – First-Time Setup (Windows)
:: ==============================================================
:: Creates a virtual environment, installs dependencies, and
:: initializes the database.
::
:: Prerequisites:
::   - Python 3.10+ installed and on PATH
::   - .env file configured in the project root
::   - psql CLI on PATH (only needed for DB setup)
::
:: Usage: double-click or run  scripts\setup.bat
:: ==============================================================

setlocal enabledelayedexpansion

:: Navigate to project root (one level up from scripts\)
cd /d "%~dp0\.."
set "PROJECT_ROOT=%cd%"
echo ============================================
echo   Clerasense – Setup
echo ============================================
echo Project root: %PROJECT_ROOT%
echo.

:: ---- Check Python ----
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not on PATH.
    echo        Download from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: ---- Create virtual environment ----
if not exist "venv\Scripts\activate.bat" (
    echo ==> Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo     Virtual environment created.
) else (
    echo ==> Virtual environment already exists.
)
echo.

:: ---- Activate venv ----
call venv\Scripts\activate.bat

:: ---- Install dependencies ----
echo ==> Installing Python dependencies...
pip install --upgrade pip >nul 2>&1
pip install -r backend\requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Dependency installation failed.
    pause
    exit /b 1
)
echo     Dependencies installed.
echo.

:: ---- Check .env ----
if not exist ".env" (
    echo WARNING: .env file not found in %PROJECT_ROOT%
    echo          Create one with DATABASE_URL, OPENAI_API_KEY, etc.
    echo          See README.md for required variables.
    echo.
)

echo ============================================
echo   Setup complete!
echo ============================================
echo.
echo Next steps:
echo   1. Make sure your .env is configured
echo   2. Run  scripts\setup_db.bat   to initialize the database
echo   3. Run  scripts\run.bat        to start the server
echo.
pause
