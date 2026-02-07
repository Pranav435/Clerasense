@echo off
:: ==============================================================
:: Clerasense – Database Schema ^& Seed Setup (Windows)
:: ==============================================================
:: Runs schema migration and seed data against the DATABASE_URL
:: defined in your .env file.
::
:: Prerequisites:
::   - psql CLI installed and on PATH
::     (comes with PostgreSQL, or install via: scoop install postgresql)
::   - DATABASE_URL set in .env
::
:: Usage: double-click or run  scripts\setup_db.bat
:: ==============================================================

setlocal enabledelayedexpansion

cd /d "%~dp0\.."
set "PROJECT_ROOT=%cd%"

echo ============================================
echo   Clerasense – Database Setup
echo ============================================
echo.

:: ---- Check psql ----
where psql >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: psql is not installed or not on PATH.
    echo        Install PostgreSQL or add its bin folder to PATH.
    echo        e.g. C:\Program Files\PostgreSQL\16\bin
    pause
    exit /b 1
)

:: ---- Read DATABASE_URL from .env ----
if not exist ".env" (
    echo ERROR: .env file not found at %PROJECT_ROOT%\.env
    echo        Create it with your DATABASE_URL.
    pause
    exit /b 1
)

set "DATABASE_URL="
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if "%%A"=="DATABASE_URL" set "DATABASE_URL=%%B"
)

if "%DATABASE_URL%"=="" (
    echo ERROR: DATABASE_URL is not set in .env
    pause
    exit /b 1
)

:: ---- Run schema ----
echo ==> Running schema migration...
psql "%DATABASE_URL%" -f "%PROJECT_ROOT%\database\schema.sql"
if %errorlevel% neq 0 (
    echo ERROR: Schema migration failed.
    pause
    exit /b 1
)
echo     Schema applied.
echo.

:: ---- Run seed ----
echo ==> Seeding reference data...
psql "%DATABASE_URL%" -f "%PROJECT_ROOT%\database\seed.sql"
if %errorlevel% neq 0 (
    echo ERROR: Seed data insertion failed.
    pause
    exit /b 1
)
echo     Seed data loaded.
echo.

echo ============================================
echo   Database is ready!
echo ============================================
pause
