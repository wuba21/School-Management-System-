@echo off
REM ============================================================
REM  SSMS — Start LAN Server (Windows Batch Script)
REM  Metti Secondary School
REM  Double-click this file to start the school management server
REM ============================================================

TITLE SSMS - Smart School Management System - LAN Server

echo.
echo  =========================================================
echo   Smart School Management and Academic Information System
echo   Metti Secondary School - Metti, Majang Zone, Gambella
echo  =========================================================
echo.

REM Change to the project directory (adjust path if installed elsewhere)
cd /d "%~dp0.."

REM Activate the Python virtual environment
echo [*] Activating Python virtual environment...
call venv\Scripts\activate.bat

IF ERRORLEVEL 1 (
    echo [ERROR] Failed to activate virtual environment.
    echo         Make sure venv\ exists in the project folder.
    pause
    exit /b 1
)

echo [OK] Virtual environment activated.
echo.

REM Start the production server
echo [*] Starting SSMS LAN server...
echo [*] Other computers can connect at: http://^<this-computer-ip^>:8000/
echo.
echo     To find this computer's IP address, open Command Prompt and type:
echo       ipconfig
echo     Look for "IPv4 Address" under your network adapter.
echo.

python scripts\serve_lan.py --host 0.0.0.0 --port 8000 --threads 8

echo.
echo [*] SSMS server has stopped.
pause
