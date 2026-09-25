@echo off
title FLOWDEV FRAME WORKSTATION
cd /d "%~dp0"
echo =========================================================================
echo       LAUNCHING FLOWDEV FRAME WORKSTATION (INTERNAL DEV BUILD)
echo =========================================================================
echo Target Python: c:\Ngoding\xau_deep_sniper\.venv\Scripts\python.exe
echo.
c:\Ngoding\xau_deep_sniper\.venv\Scripts\python.exe launch_workstation.py
pause
