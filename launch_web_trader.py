"""
FLOWDEV FRAME // 24/7 CLOUD WEB WORKSTATION LAUNCHER
Launches the full Streamlit Web Application on port 8501.
Features:
- Live Real-Time Trader matching Desktop Station
- Live Trades Database Performance Evaluator
- Quantitative Historical Backtest Workstation
- Cron-Job.org Keep-Alive endpoint for 24/7 online cloud execution
"""

import sys, pathlib, subprocess

workspace_root = pathlib.Path(__file__).resolve().parent
streamlit_script = workspace_root / "src" / "frame" / "live" / "web_app.py"

# Use virtualenv with streamlit
python_exe = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\.venv\Scripts\python.exe")
if not python_exe.exists():
    python_exe = pathlib.Path(sys.executable)

cmd = [
    str(python_exe),
    "-m", "streamlit", "run",
    str(streamlit_script),
    "--server.port=8501",
    "--server.headless=true",
    "--theme.base=dark"
]

print("=========================================================================")
print("      LAUNCHING FLOWDEV FRAME // CLOUD WEB WORKSTATION")
print("=========================================================================")
print(f"Target Script: {streamlit_script}")
print("Local URL    : http://localhost:8501")
print("Network URL  : http://<YOUR_IP>:8501")
print("=========================================================================\n")

subprocess.run(cmd, cwd=str(workspace_root))
