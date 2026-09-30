"""
FLOWDEV FRAME - Enterprise Quantitative Trading Cockpit Launcher
Unified Desktop Application combining Live Trader and Causal Backtest Station.
"""

import sys, pathlib, os

# Ensure workspace root is in sys.path
app_root = pathlib.Path(__file__).resolve().parent
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

from src.frame.gui.frame_cockpit import run_frame_app

if __name__ == "__main__":
    run_frame_app()
