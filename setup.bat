@echo off
echo ========================================
echo  Facebook Posting - Full Setup
echo  SQLite + Python + Frontend
echo ========================================
cd /d "%~dp0"

echo.
echo [1/4] Python virtual environment...
cd backend
if not exist "venv" (
    python -m venv venv
)
call venv\Scripts\activate
if not exist ".env" copy .env.example .env
echo Installing Python packages...
pip install -r requirements.txt
if errorlevel 1 (
    echo Python install failed.
    pause
    exit /b 1
)

echo.
echo [2/4] SQLite database...
if not exist "data" mkdir data
python -c "from app.config import get_settings; from app.startup_db import run_blocking_startup; run_blocking_startup(get_settings()); print('SQLite ready: data/facebook_posting.db')"
if errorlevel 1 (
    echo Database init failed.
    pause
    exit /b 1
)

echo.
echo [3/4] Frontend npm packages...
cd ..\frontend
call npm install
if errorlevel 1 (
    echo npm install failed.
    pause
    exit /b 1
)

echo.
echo [4/4] Playwright Chromium (~180 MB, required for Start ON)...
cd ..\backend
set PLAYWRIGHT_BROWSERS_PATH=%~dp0backend\playwright-browsers
python scripts\ensure_playwright_chromium.py
if errorlevel 1 (
    echo Chromium install failed. Check internet and run install-chromium.bat
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Setup complete!
echo.
echo  1. Double-click startall.bat
echo  2. Open http://localhost:5174
echo  3. Set admin email and password (first visit), then log in
echo ========================================
pause
