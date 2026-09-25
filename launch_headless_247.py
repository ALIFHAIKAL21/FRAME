"""
FLOWDEV FRAME // 24/7 HEADLESS LIVE TRADER LAUNCHER
Runs the live market agent in ultra-lightweight background daemon mode.
Can run continuously without any desktop window, on a cloud VPS or background process.
"""

import sys, pathlib

current_dir = pathlib.Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from src.frame.live.headless_runner import main

if __name__ == "__main__":
    main()
