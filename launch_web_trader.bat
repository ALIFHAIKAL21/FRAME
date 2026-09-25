@echo off
title FLOWDEV FRAME - CLOUD WEB WORKSTATION
cd /d "%~dp0"
echo =========================================================================
echo       LAUNCHING FLOWDEV FRAME // CLOUD WEB WORKSTATION
echo       Modes: Live Trader, DB Live Evaluator, Historical Backtest
echo       Keep-Alive: Cron-Job.org Ready (100%% Free Cloud 24/7)
echo =========================================================================
echo Target Python: c:\Ngoding\xau_deep_sniper\.venv\Scripts\python.exe
echo.
c:\Ngoding\xau_deep_sniper\.venv\Scripts\python.exe launch_web_trader.py
pause
