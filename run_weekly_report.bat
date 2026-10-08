@echo off
cd /d C:\RPi_Monitor
py -3 weekly_report.py 7 >> C:\RPi_Monitor\scheduler_output.txt 2>&1
