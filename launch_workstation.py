"""
FLOWDEV FRAME WORKSTATION // DESKTOP LAUNCHER
Single-click launcher for the internal development and backtest workstation.
"""

import sys, pathlib

# Ensure workspace root is in python path
current_dir = pathlib.Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from src.frame.gui.app import run_app

if __name__ == "__main__":
    run_app()
