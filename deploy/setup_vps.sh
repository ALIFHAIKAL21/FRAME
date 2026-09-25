#!/bin/bash
# ==============================================================================
# 24/7 VPS Auto-Setup Script for Quant Trading Bot & Streamlit Dashboard
# Supported OS: Ubuntu 22.04 / 24.04 LTS, Debian 12
# ==============================================================================
set -e

echo "=== 1. Updating System Packages ==="
sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv curl git build-essential

echo "=== 2. Installing uv for ultra-fast Python environment ==="
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "=== 3. Creating Virtual Environment & Installing Dependencies ==="
uv venv .venv --python 3.10
uv pip install -r requirements.txt --python .venv/bin/python

mkdir -p logs data reports

echo "=== 4. Setting up systemd background services (Auto-Restart 24/7) ==="
APP_DIR=$(pwd)
CURRENT_USER=$(whoami)

# Scalper Service
cat <<EOF | sudo tee /etc/systemd/system/quant-scalper.service
[Unit]
Description=Quant Trading 5m Scalper Daemon
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/.venv/bin/python run.py --scalp-live
Restart=always
RestartSec=10
StandardOutput=append:${APP_DIR}/logs/scalper_stdout.log
StandardError=append:${APP_DIR}/logs/scalper_stderr.log

[Install]
WantedBy=multi-user.target
EOF

# Dashboard Service
cat <<EOF | sudo tee /etc/systemd/system/quant-dashboard.service
[Unit]
Description=Quant Trading Streamlit Dashboard
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/.venv/bin/python -m streamlit run src/dashboard/app.py --server.port 8502 --server.address 0.0.0.0 --server.headless true
Restart=always
RestartSec=10
StandardOutput=append:${APP_DIR}/logs/dashboard_stdout.log
StandardError=append:${APP_DIR}/logs/dashboard_stderr.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable quant-scalper.service
sudo systemctl enable quant-dashboard.service

sudo systemctl restart quant-scalper.service
sudo systemctl restart quant-dashboard.service

echo "=============================================================================="
echo " [SUCCESS] 24/7 Scalper and Dashboard are now running in the background!"
echo " Scalper Status:   sudo systemctl status quant-scalper.service"
echo " Dashboard Status: sudo systemctl status quant-dashboard.service"
echo " View Logs:        tail -f logs/scalper_stdout.log"
echo " Open Dashboard:   http://<YOUR-SERVER-IP>:8502"
echo "=============================================================================="
