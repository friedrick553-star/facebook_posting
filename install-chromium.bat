@echo off
echo ========================================
echo  Install Playwright Chromium (ONE TIME)
echo ========================================
cd /d "%~dp0backend"
call venv\Scripts\activate
set PLAYWRIGHT_BROWSERS_PATH=%~dp0backend\playwright-browsers
python scripts\ensure_playwright_chromium.py
if errorlevel 1 (
    echo.
    echo Install failed. Check internet and try again.
    pause
    exit /b 1
)
echo.
echo Done. Chromium is in backend\playwright-browsers
echo Now run startall.bat and press Start ON.
pause
