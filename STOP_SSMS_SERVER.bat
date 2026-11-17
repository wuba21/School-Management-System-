@echo off
REM ============================================================
REM  SSMS — Stop LAN Server (Windows Batch Script)
REM  Finds and cleanly stops the Python/Waitress process
REM ============================================================

TITLE SSMS - Stop Server

echo.
echo  Stopping SSMS LAN Server...
echo.

REM Find and kill the Python process running serve_lan.py
for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fo list ^| find "PID:"') do (
    taskkill /pid %%i /f >nul 2>&1
    if not errorlevel 1 echo [OK] Stopped Python process PID %%i
)

echo.
echo  SSMS server stopped.
echo.
pause
