@echo off
REM Run this ONCE as Administrator. Change times if you want.
REM Daily check at 09:00
schtasks /create /tn "RPi Daily Check" /tr "C:\RPi_Monitor\run_daily_check.bat" /sc daily /st 09:00 /rl highest /f
REM Weekly report every Monday 09:30
schtasks /create /tn "RPi Weekly Report" /tr "C:\RPi_Monitor\run_weekly_report.bat" /sc weekly /d MON /st 09:30 /rl highest /f
echo.
echo Done. Now open Task Scheduler and for BOTH tasks set:
echo   - "Run whether user is logged on or not"
echo   - Settings tab: "Run task as soon as possible after a scheduled start is missed"
pause
