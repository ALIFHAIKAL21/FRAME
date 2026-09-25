"""
FLOWDEV FRAME // LIVE REALTIME TRADER LAUNCHER
Dedicated standalone launcher for live real-time market paper-trading simulation.
Runs the optimal MOMENT 15-channel neural model with 4-stage kinetic OMS in real time.
"""

import sys, pathlib

# Ensure workspace root is in python path
current_dir = pathlib.Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from src.frame.live.live_window import run_live_app

if __name__ == "__main__":
    run_live_app()
