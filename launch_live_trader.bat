@echo off
title FLOWDEV FRAME - LIVE REALTIME TRADER [ZERO ACCOUNT RISK]
cd /d "%~dp0"
echo =========================================================================
echo       LAUNCHING FLOWDEV FRAME - LIVE REALTIME PAPER TRADER
echo       Model: MOMENT 15-Channel LoRA + 4-Stage Kinetic OMS
echo       Mode: Live Realtime Simulation (Zero Real Account Risk)
echo =========================================================================
echo Target Python: c:\Ngoding\xau_deep_sniper\.venv\Scripts\python.exe
echo.
c:\Ngoding\xau_deep_sniper\.venv\Scripts\python.exe launch_live_trader.py
pause
