@echo off
cd /d C:\RPi_Monitor
py -3 rpi_daily_check.py >> C:\RPi_Monitor\scheduler_output.txt 2>&1
