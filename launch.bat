@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

title AI Email Intelligence Platform

echo.
echo =============================================================
echo   AI EMAIL INTELLIGENCE PLATFORM
echo   Final Year Generative AI Project
echo =============================================================
echo.

REM ---- Check Python ------------------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in your PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo and make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python !PYVER! detected

REM ---- Create virtual environment ---------------------------------------
if not exist "venv\" (
    echo.
    echo First-time setup: creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Could not create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
)

REM ---- Activate venv & install dependencies -----------------------------
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Could not activate virtual environment.
    pause
    exit /b 1
)

REM Check if Flask is installed (proxy for whether deps are installed)
python -c "import flask" 2>nul
if errorlevel 1 (
    echo.
    echo Installing dependencies... this may take 1-2 minutes on first run.
    python -m pip install --upgrade pip --quiet
    python -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [ERROR] Could not install dependencies.
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed
) else (
    echo [OK] Dependencies already installed
)

REM ---- Launch the server + browser --------------------------------------
echo.
echo =============================================================
echo   Starting server on http://localhost:5000
echo   The browser will open automatically in ~3 seconds
echo   Press Ctrl+C in this window to stop the server
echo =============================================================
echo.

REM Open the browser after a short delay so the server has time to start
start "" cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:5000"

REM Start the app in the foreground
python app.py

REM If the app exits, keep the window open so the user can see any errors
echo.
echo Server stopped.
pause
