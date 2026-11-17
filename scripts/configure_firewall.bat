@echo off
REM ============================================================
REM  SSMS — Configure Windows Firewall for LAN Access
REM  Metti Secondary School - Offline LAN Deployment
REM  
REM  Run as Administrator to allow inbound traffic on port 8000
REM  so other workstations on the school LAN can connect.
REM ============================================================

TITLE SSMS - Configure Windows Firewall

echo.
echo  =========================================================
echo   SSMS Windows Firewall Configuration
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

echo [*] Adding Windows Defender Firewall Rule for Port 8000 (Inbound)...

netsh advfirewall firewall add rule name="SSMS School Management System (Port 8000)" dir=in action=allow protocol=TCP localport=8000 profile=private,domain description="Allows workstations on Metti Secondary School LAN to access SSMS server on port 8000"

if %errorLevel% equ 0 (
    echo [OK] Firewall rule created successfully!
    echo.
    echo Workstations on the school network can now connect to:
    echo   http://^<server-ip^>:8000/
) else (
    echo [ERROR] Failed to add firewall rule. Error code: %errorLevel%
)

echo.
pause
