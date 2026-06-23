@echo off
cd /d "%~dp0"

if not exist "backend\venv\Scripts\python.exe" (
    echo First time: run setup.bat then startall.bat again.
    pause
    exit /b 1
)

echo Stopping any running backend and frontend...
if exist "backend\data\backend.pid" (
    for /f %%p in (backend\data\backend.pid) do (
        echo   Backend PID %%p
        taskkill /PID %%p /F >nul 2>&1
    )
    del /f /q "backend\data\backend.pid" >nul 2>&1
)

for %%P in (8002 5174) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%P" ^| findstr "LISTENING"') do (
        echo   Port %%P PID %%a
        taskkill /PID %%a /F >nul 2>&1
    )
)

ping -n 3 127.0.0.1 >nul

start "FB Posting Backend" cmd /k "%~dp0_internal\boot-backend.bat"
ping -n 9 127.0.0.1 >nul
start "FB Posting Frontend" cmd /k "%~dp0_internal\boot-frontend.bat"
ping -n 4 127.0.0.1 >nul
start "" "http://localhost:5174"

echo.
echo App: http://localhost:5174
echo Keep both CMD windows open (backend + frontend).
echo.
