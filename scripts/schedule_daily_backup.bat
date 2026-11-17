@echo off
REM ============================================================
REM  SSMS — Windows Scheduled Daily Backup Task Creator
REM  Metti Secondary School - Offline LAN Deployment
REM  
REM  Run as Administrator to register an automated daily backup
REM  at 18:00 (6:00 PM) everyday via Windows Task Scheduler.
REM ============================================================

TITLE SSMS - Register Daily Backup Task

echo.
echo  =========================================================
echo   SSMS Automated Daily Backup Registration
echo   Metti Secondary School - Godere Woreda, Majang Zone
echo  =========================================================
echo.

REM Verify Administrator Privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Administrative permissions required.
    echo         Please right-click this script and select:
    echo         "Run as administrator"
    echo.
    pause
    exit /b 1
)

set SCRIPT_DIR=%~dp0..
set BACKUP_BAT=%SCRIPT_DIR%\scripts\run_backup_job.bat

echo [*] Creating backup runner script at %BACKUP_BAT%...

(
echo @echo off
echo cd /d "%SCRIPT_DIR%"
echo call venv\Scripts\activate.bat
echo python manage.py backup_database ^>^> logs\backup_task.log 2^>^&1
echo python manage.py backup_media ^>^> logs\backup_task.log 2^>^&1
echo python manage.py prune_backups ^>^> logs\backup_task.log 2^>^&1
) > "%BACKUP_BAT%"

echo [OK] Backup runner created.
echo.
echo [*] Registering Windows Scheduled Task "SSMS_Daily_Backup" at 18:00 daily...

schtasks /create /tn "SSMS_Daily_Backup" /tr "\"%BACKUP_BAT%\"" /sc daily /st 18:00 /f /rl highest

if %errorLevel% equ 0 (
    echo.
    echo [OK] Windows Scheduled Task "SSMS_Daily_Backup" registered successfully!
    echo      The task will automatically run every day at 6:00 PM (18:00).
    echo      Logs will be written to: %SCRIPT_DIR%\logs\backup_task.log
) else (
    echo.
    echo [ERROR] Failed to register scheduled task. Error code: %errorLevel%
)

echo.
pause
