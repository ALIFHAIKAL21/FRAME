"""
FLOWDEV FRAME - Desktop Institutional Security Gatekeeper Dialog
Provides high-aesthetic operator authentication before unlocking the live workstation.
Features:
- Fast 6-Digit PIN keypad entry.
- Full Operator Credentials (Username + Cryptographic Password).
- Anti-brute-force rate limiting with cooldown timer.
- Trusted workstation session persistence.
"""

import sys, pathlib, json
from typing import Optional, Dict, Any

try:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
        QFrame, QTabWidget, QWidget, QCheckBox, QMessageBox, QApplication
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QFont, QColor, QIcon
except ImportError:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
        QFrame, QTabWidget, QWidget, QCheckBox, QMessageBox, QApplication
    )
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QFont, QColor, QIcon

from .auth import AdvancedAuthManager

TRUSTED_SESSION_FILE = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\logs\trusted_desktop_session.json")

class DesktopAuthGatekeeper(QDialog):
    def __init__(self, parent=None, is_lock_screen: bool = False):
        super().__init__(parent)
        self.auth = AdvancedAuthManager()
        self.authenticated_user: Optional[Dict[str, Any]] = None
        self.is_lock_screen = is_lock_screen
        
        self.setWindowTitle("FLOWDEV FRAME // SECURITY GATEKEEPER")
        self.setFixedSize(450, 420)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #07090e;
                color: #e2e8f0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            QFrame#card {
                background-color: #0b0f19;
                border: 1px solid #1e293b;
                border-radius: 6px;
            }
            QLabel { color: #cbd5e1; font-size: 11px; }
            QLineEdit {
                background-color: #05070b;
                border: 1px solid #27334a;
                border-radius: 4px;
                padding: 8px 12px;
                color: #f8fafc;
                font-size: 13px;
                font-family: monospace;
            }
            QLineEdit:focus { border: 1px solid #00e676; background-color: #080c14; }
            QPushButton#btn_primary {
                background-color: #004d40;
                border: 1px solid #00bfa5;
                color: #ffffff;
                font-size: 12px;
                font-weight: 800;
                padding: 10px;
                border-radius: 4px;
            }
            QPushButton#btn_primary:hover { background-color: #00695c; }
            QPushButton#btn_cancel {
                background-color: #1e293b;
                border: 1px solid #334155;
                color: #94a3b8;
                font-size: 11px;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton#btn_cancel:hover { background-color: #334155; color: #f1f5f9; }
            QTabWidget::pane { border: 1px solid #1e293b; background-color: #090d14; border-radius: 4px; }
            QTabBar::tab {
                background-color: #0f172a;
                color: #94a3b8;
                padding: 8px 18px;
                font-weight: 700;
                font-size: 11px;
                border: 1px solid #1e293b;
            }
            QTabBar::tab:selected { background-color: #1e293b; color: #38bdf8; border-bottom: 2px solid #00e676; }
        """)

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # Header Title
        title_box = QFrame()
        title_box.setStyleSheet("background-color: transparent;")
        t_layout = QVBoxLayout(title_box)
        t_layout.setContentsMargins(0, 0, 0, 0)
        t_layout.setSpacing(2)

        lbl_falcon = QLabel("🦅 FLOWDEV FRAME // OPERATOR AUTHENTICATION")
        lbl_falcon.setStyleSheet("font-size: 12px; font-weight: 800; color: #d4af37; letter-spacing: 1.2px;")
        t_layout.addWidget(lbl_falcon)

        lbl_sub = QLabel("Institutional Multi-Factor Security Clearance" if not self.is_lock_screen else "Workstation Session Locked. Enter PIN to resume.")
        lbl_sub.setStyleSheet("font-size: 10.5px; color: #8b949e;")
        t_layout.addWidget(lbl_sub)
        main_layout.addWidget(title_box)

        # Tab Widget for PIN vs Password
        self.tabs = QTabWidget()

        # Tab 1: Fast 6-Digit PIN
        tab_pin = QWidget()
        pin_layout = QVBoxLayout(tab_pin)
        pin_layout.setContentsMargins(14, 14, 14, 14)
        pin_layout.setSpacing(10)

        pin_layout.addWidget(QLabel("Enter 6-Digit Operator PIN:"))
        self.txt_pin = QLineEdit()
        self.txt_pin.setEchoMode(QLineEdit.Password)
        self.txt_pin.setMaxLength(6)
        self.txt_pin.setPlaceholderText("••••••")
        self.txt_pin.setAlignment(Qt.AlignCenter)
        self.txt_pin.setStyleSheet("font-size: 20px; letter-spacing: 6px; font-weight: 800; color: #00e676;")
        self.txt_pin.returnPressed.connect(self._handle_pin_submit)
        pin_layout.addWidget(self.txt_pin)

        btn_pin = QPushButton("🔓 UNLOCK WORKSTATION")
        btn_pin.setObjectName("btn_primary")
        btn_pin.clicked.connect(self._handle_pin_submit)
        pin_layout.addWidget(btn_pin)

        pin_layout.addStretch()
        lbl_pin_hint = QLabel("Default Master PIN: 789012  |  Auditor PIN: 123456")
        lbl_pin_hint.setStyleSheet("font-size: 9.5px; color: #64748b; font-family: monospace;")
        pin_layout.addWidget(lbl_pin_hint)
        self.tabs.addTab(tab_pin, "🔑 QUICK PIN")

        # Tab 2: Full Credentials
        tab_cred = QWidget()
        cred_layout = QVBoxLayout(tab_cred)
        cred_layout.setContentsMargins(14, 14, 14, 14)
        cred_layout.setSpacing(8)

        cred_layout.addWidget(QLabel("Operator Username:"))
        self.txt_user = QLineEdit()
        self.txt_user.setPlaceholderText("alifhaikal")
        cred_layout.addWidget(self.txt_user)

        cred_layout.addWidget(QLabel("Master Password:"))
        self.txt_pass = QLineEdit()
        self.txt_pass.setEchoMode(QLineEdit.Password)
        self.txt_pass.setPlaceholderText("••••••••••••")
        self.txt_pass.returnPressed.connect(self._handle_pass_submit)
        cred_layout.addWidget(self.txt_pass)

        btn_pass = QPushButton("🔐 VERIFY CREDENTIALS")
        btn_pass.setObjectName("btn_primary")
        btn_pass.clicked.connect(self._handle_pass_submit)
        cred_layout.addWidget(btn_pass)
        self.tabs.addTab(tab_cred, "👤 FULL LOGIN")

        main_layout.addWidget(self.tabs)

        # Status & Message label
        self.lbl_msg = QLabel("")
        self.lbl_msg.setStyleSheet("font-size: 11px; font-weight: 700; color: #ff5252;")
        self.lbl_msg.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.lbl_msg)

        # Bottom Actions
        b_box = QHBoxLayout()
        self.chk_trust = QCheckBox("Remember trusted desktop session (12 Hours)")
        self.chk_trust.setChecked(True)
        self.chk_trust.setStyleSheet("color: #8b949e; font-size: 10.5px;")
        b_box.addWidget(self.chk_trust)

        btn_exit = QPushButton("Cancel / Exit")
        btn_exit.setObjectName("btn_cancel")
        btn_exit.clicked.connect(self.reject)
        b_box.addWidget(btn_exit)
        main_layout.addLayout(b_box)

        # Focus PIN on startup
        QTimer.singleShot(100, self.txt_pin.setFocus)

    def _handle_pin_submit(self):
        pin = self.txt_pin.text().strip()
        if len(pin) < 4:
            self.lbl_msg.setText("Masukkan minimal 4 hingga 6 digit PIN.")
            return

        ok, msg, user = self.auth.authenticate_pin(pin, source="DESKTOP")
        if ok:
            self.authenticated_user = user
            if self.chk_trust.isChecked():
                self._save_trusted_session(user)
            self.accept()
        else:
            self.lbl_msg.setText(msg)
            self.txt_pin.clear()
            self.txt_pin.setFocus()

    def _handle_pass_submit(self):
        u = self.txt_user.text().strip()
        p = self.txt_pass.text().strip()
        if not u or not p:
            self.lbl_msg.setText("Username dan password tidak boleh kosong.")
            return

        ok, msg, user = self.auth.authenticate_password(u, p, source="DESKTOP")
        if ok:
            self.authenticated_user = user
            if self.chk_trust.isChecked():
                self._save_trusted_session(user)
            self.accept()
        else:
            self.lbl_msg.setText(msg)
            self.txt_pass.clear()
            self.txt_pass.setFocus()

    def _save_trusted_session(self, user: Dict[str, Any]):
        try:
            TRUSTED_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(TRUSTED_SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(user, f, indent=2)
        except Exception:
            pass

    @classmethod
    def try_restore_session(cls) -> Optional[Dict[str, Any]]:
        """Attempts to restore an unexpired trusted desktop session."""
        try:
            if TRUSTED_SESSION_FILE.exists():
                with open(TRUSTED_SESSION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                tok = data.get("token", "")
                auth = AdvancedAuthManager()
                verified = auth.verify_session_token(tok)
                if verified:
                    auth.db.record_auth_event(
                        verified["username"], verified["role"],
                        "SESSION_RESTORE", "DESKTOP", "SUCCESS", "Trusted desktop session auto-unlocked"
                    )
                    return verified
        except Exception:
            pass
        return None

    @classmethod
    def clear_session(cls):
        try:
            if TRUSTED_SESSION_FILE.exists():
                TRUSTED_SESSION_FILE.unlink()
        except Exception:
            pass
