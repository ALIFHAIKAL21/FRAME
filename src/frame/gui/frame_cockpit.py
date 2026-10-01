"""
FLOWDEV FRAME - Master Quantitative Desktop Cockpit
Unified Single-Window Enterprise Terminal combining:
- Tab 0: 🔴 LIVE REALTIME TRADER (Sub-second chart, Kinetic 4-stage OMS, live feed, paper broker, Neon DB & Cloud sync)
- Tab 1: ⚡ CAUSAL BACKTEST STATION (Locked MOMENT-1 model, 15-channel analytics, TradingView inspector, monthly breakdown)
"""

import sys, pathlib, json, time, threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QStackedWidget, QFrame, QMessageBox, QDialog
)
from PySide6.QtCore import Qt, QTimer, QLocale
from PySide6.QtGui import QFont, QColor, QIcon, QPixmap

# Ensure workspace root is in sys.path
project_root = pathlib.Path(__file__).resolve().parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.frame.gui.styles import QSS_STYLE
from src.frame.live.live_window import LiveTradingWindow
from src.frame.gui.app import MainWindow as BacktestMainWindow
from src.frame.security.auth_dialog import DesktopAuthGatekeeper


class FrameMasterCockpit(QMainWindow):
    """
    Unified Master Desktop Application 'FRAME'
    Seamlessly integrates Live Trading and Backtest Station in a single window with tabs.
    """
    def __init__(self, operator_user: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.operator_user = operator_user or {
            "username": "alifhaikal",
            "role": "MASTER_TRADER",
            "display_name": "Alif Haikal (Master Operator)"
        }
        self.setWindowTitle("FRAME // QUANTITATIVE ENTERPRISE DESKTOP TERMINAL")
        self.resize(1440, 930)
        self.setMinimumSize(1200, 780)
        self.setStyleSheet(QSS_STYLE)

        icon_file = project_root / "assets" / "frame_icon.ico"
        if icon_file.exists():
            self.setWindowIcon(QIcon(str(icon_file)))

        # Instantiate the two specialized workstations
        self.live_workstation = LiveTradingWindow(operator_user=self.operator_user)
        self.backtest_workstation = BacktestMainWindow(operator_user=self.operator_user)

        self._init_master_ui()
        self._wire_tab_buttons()

    def _init_master_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(6, 4, 6, 6)
        root_layout.setSpacing(4)

        # -------------------------------------------------------------
        # Master Global Header Bar
        # -------------------------------------------------------------
        header = QFrame()
        header.setFixedHeight(48)
        header.setStyleSheet("background-color: #06090e; border: 1px solid #1a2230; border-radius: 4px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 2, 12, 2)
        h_layout.setSpacing(10)

        # Logo / Brand
        lbl_brand = QLabel("FRAME")
        lbl_brand.setStyleSheet("font-size: 15px; font-weight: 900; color: #ffd700; letter-spacing: 2px;")
        h_layout.addWidget(lbl_brand)

        lbl_sep = QLabel("•")
        lbl_sep.setStyleSheet("color: #334155; font-size: 14px;")
        h_layout.addWidget(lbl_sep)

        # Master Navigation Tabs
        self.btn_tab_live = QPushButton("🔴 LIVE REALTIME TRADER")
        self.btn_tab_live.setCursor(Qt.PointingHandCursor)
        self.btn_tab_live.setToolTip("Switch to Live Real-Time Market Simulation Workstation")
        h_layout.addWidget(self.btn_tab_live)

        self.btn_tab_backtest = QPushButton("⚡ CAUSAL BACKTEST STATION")
        self.btn_tab_backtest.setCursor(Qt.PointingHandCursor)
        self.btn_tab_backtest.setToolTip("Switch to Causal Historical Backtest & Analytics Workstation")
        h_layout.addWidget(self.btn_tab_backtest)

        h_layout.addSpacing(15)

        # Forward status badges from live workstation
        self.lbl_cloud = self.live_workstation.lbl_cloud_status
        h_layout.addWidget(self.lbl_cloud)

        self.lbl_feed = self.live_workstation.lbl_feed_status
        h_layout.addWidget(self.lbl_feed)

        h_layout.addStretch()

        # Telemetry info
        lbl_device = QLabel("[RTX 4090 / CUDA 12.6] [XAU/USD M30]")
        lbl_device.setStyleSheet("font-size: 10px; font-family: monospace; color: #64748b;")
        h_layout.addWidget(lbl_device)

        # Operator Badge
        self.lbl_operator = QLabel(f"👤 {self.operator_user.get('display_name', 'OPERATOR').upper()}")
        self.lbl_operator.setStyleSheet("font-size: 10px; font-weight: 800; color: #38bdf8; background-color: #0f172a; padding: 4px 10px; border: 1px solid #1e293b; border-radius: 3px;")
        h_layout.addWidget(self.lbl_operator)

        # Master Lock Button
        btn_lock = QPushButton("🔒 LOCK")
        btn_lock.setToolTip("Lock Desktop Terminal Session")
        btn_lock.setStyleSheet("""
            QPushButton {
                background-color: #1e293b; border: 1px solid #334155;
                font-size: 10px; padding: 4px 8px; font-weight: 700; color: #94a3b8; border-radius: 3px;
            }
            QPushButton:hover { background-color: #334155; color: #f8fafc; border-color: #ef4444; }
        """)
        btn_lock.clicked.connect(self._lock_session)
        h_layout.addWidget(btn_lock)

        root_layout.addWidget(header)

        # -------------------------------------------------------------
        # Central Stacked Container
        # -------------------------------------------------------------
        self.stack = QStackedWidget()

        # Tab 0: Live Trader central widget (Clean, duplicate internal header hidden)
        w_live = self.live_workstation.centralWidget()
        if hasattr(self.live_workstation, "header_frame"):
            self.live_workstation.header_frame.setVisible(False)
        self.stack.addWidget(w_live)

        # Tab 1: Backtest central widget (Clean, duplicate internal header hidden)
        w_bt = self.backtest_workstation.centralWidget()
        if hasattr(self.backtest_workstation, "header_frame"):
            self.backtest_workstation.header_frame.setVisible(False)
        self.stack.addWidget(w_bt)

        root_layout.addWidget(self.stack, stretch=1)

        # Initialize to Tab 0 (Live Trader)
        self.switch_tab(0)

    def _wire_tab_buttons(self):
        self.btn_tab_live.clicked.connect(lambda: self.switch_tab(0))
        self.btn_tab_backtest.clicked.connect(lambda: self.switch_tab(1))

        # Re-route the internal cross-window buttons to tab switches instead!
        if hasattr(self.live_workstation, 'btn_switch_historical'):
            self.live_workstation.btn_switch_historical.clicked.disconnect()
            self.live_workstation.btn_switch_historical.clicked.connect(lambda: self.switch_tab(1))

        if hasattr(self.backtest_workstation, 'btn_live'):
            self.backtest_workstation.btn_live.clicked.disconnect()
            self.backtest_workstation.btn_live.clicked.connect(lambda: self.switch_tab(0))

    def switch_tab(self, idx: int):
        self.stack.setCurrentIndex(idx)
        if idx == 0:
            # Live Trader Tab Active
            self.btn_tab_live.setStyleSheet("""
                QPushButton {
                    background-color: #450a0a; border: 1px solid #ef4444;
                    font-size: 11px; padding: 5px 14px; font-weight: 800; color: #fef2f2;
                    border-radius: 3px;
                }
            """)
            self.btn_tab_backtest.setStyleSheet("""
                QPushButton {
                    background-color: #0f172a; border: 1px solid #1e293b;
                    font-size: 11px; padding: 5px 14px; font-weight: 700; color: #94a3b8;
                    border-radius: 3px;
                }
                QPushButton:hover { background-color: #1e293b; color: #00e5ff; border-color: #00bfa5; }
            """)
        else:
            # Backtest Tab Active
            self.btn_tab_live.setStyleSheet("""
                QPushButton {
                    background-color: #0f172a; border: 1px solid #1e293b;
                    font-size: 11px; padding: 5px 14px; font-weight: 700; color: #94a3b8;
                    border-radius: 3px;
                }
                QPushButton:hover { background-color: #450a0a; color: #fca5a5; border-color: #ef4444; }
            """)
            self.btn_tab_backtest.setStyleSheet("""
                QPushButton {
                    background-color: #00382f; border: 1px solid #00bfa5;
                    font-size: 11px; padding: 5px 14px; font-weight: 800; color: #e6fffa;
                    border-radius: 3px;
                }
            """)

    def _lock_session(self):
        self.hide()
        dialog = DesktopAuthGatekeeper(parent=self, is_lock_screen=True)
        if dialog.exec() == QDialog.Accepted:
            self.operator_user = dialog.authenticated_user or self.operator_user
            self.lbl_operator.setText(f"👤 {self.operator_user.get('display_name', 'OPERATOR').upper()}")
            self.showNormal()
            self.raise_()
            self.activateWindow()
        else:
            QApplication.quit()

    def closeEvent(self, event):
        try:
            if hasattr(self.live_workstation, "feed") and self.live_workstation.feed is not None:
                self.live_workstation.feed.stop()
        except Exception:
            pass
        # Clean up lockfile
        lock_file = project_root / "data" / "frame_instance.lock"
        try:
            if lock_file.exists():
                lock_file.unlink(missing_ok=True)
        except Exception:
            pass
        event.accept()
        QApplication.quit()
        import os
        os._exit(0)


def _check_and_acquire_lock() -> bool:
    lock_file = project_root / "data" / "frame_instance.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    if lock_file.exists():
        try:
            with open(lock_file, "r") as f:
                old_pid = int(f.read().strip())
            import psutil, os
            if old_pid != os.getpid() and psutil.pid_exists(old_pid):
                proc = psutil.Process(old_pid)
                pname = proc.name().lower()
                if "python" in pname or "frame" in pname:
                    return False  # Already active
        except Exception:
            pass
    try:
        import os
        with open(lock_file, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    return True


def run_frame_app():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("FRAME")
    app.setOrganizationName("FLOWDEV")

    if not _check_and_acquire_lock():
        QMessageBox.warning(
            None,
            "FRAME Already Running",
            "An active instance of FLOWDEV FRAME is already running in your system.\n\n"
            "Please switch to the currently open window, or close it before launching a new session."
        )
        sys.exit(0)

    user = DesktopAuthGatekeeper.try_restore_session()
    if not user:
        gate = DesktopAuthGatekeeper()
        if gate.exec() != QDialog.Accepted:
            # Clean lock
            lock_file = project_root / "data" / "frame_instance.lock"
            if lock_file.exists(): lock_file.unlink(missing_ok=True)
            sys.exit(0)
        user = gate.authenticated_user

    master = FrameMasterCockpit(operator_user=user)
    master.show()
    exit_code = app.exec()
    lock_file = project_root / "data" / "frame_instance.lock"
    if lock_file.exists(): lock_file.unlink(missing_ok=True)
    import os
    os._exit(exit_code)


if __name__ == "__main__":
    run_frame_app()
