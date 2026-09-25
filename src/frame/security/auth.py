"""
FLOWDEV FRAME - Advanced Institutional Authentication & Operator Security Engine
Provides robust cryptographic authentication for both Desktop Workstation and Cloud Web:
- PBKDF2-HMAC-SHA256 password hashing with secure salting.
- Fast 6-digit Operator PIN verification for quick touchscreen/desktop login.
- Role-Based Access Control (RBAC): MASTER_TRADER (Full Control) vs AUDITOR_VIEWER (Read-Only).
- Anti-brute-force rate limiting with automatic lockout cooldown.
- Time-limited signed session tokens.
- Secure bypass token for Cron-Job.org 24/7 keep-alive automation.
- Audit trail logging directly into SQLite database (auth_audit_log).
"""

import os, hmac, hashlib, time, secrets, json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
import pandas as pd

from src.frame.live.db_audit import TradeAuditDB

# Default Security Configuration (can be overridden via environment variables)
DEFAULT_MASTER_USER = os.getenv("FLOWDEV_MASTER_USER", "alifhaikal")
DEFAULT_MASTER_PASS = os.getenv("FLOWDEV_MASTER_PASS", "sniper2026!")
DEFAULT_MASTER_PIN  = os.getenv("FLOWDEV_MASTER_PIN", "789012")

DEFAULT_AUDITOR_USER = os.getenv("FLOWDEV_AUDITOR_USER", "auditor")
DEFAULT_AUDITOR_PASS = os.getenv("FLOWDEV_AUDITOR_PASS", "audit123")
DEFAULT_AUDITOR_PIN  = os.getenv("FLOWDEV_AUDITOR_PIN", "123456")

DEFAULT_CRON_SECRET  = os.getenv("FLOWDEV_CRON_KEY", "cron_secret_flowdev_falcon_2026")
JWT_SECRET_KEY       = os.getenv("FLOWDEV_JWT_SECRET", "falcon_jwt_signing_key_quantum_2026_xau")

MAX_FAILED_ATTEMPTS  = 5
LOCKOUT_DURATION_SEC = 300  # 5 minutes

class AdvancedAuthManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(AdvancedAuthManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.db = TradeAuditDB()
        
        # In-memory tracking for rate-limiting
        # { ip_or_user: {"failed_count": int, "lockout_until": float} }
        self._failed_attempts: Dict[str, Dict[str, Any]] = {}
        
        # Generate initial password hashes
        self._users = {
            DEFAULT_MASTER_USER: {
                "salt": secrets.token_hex(16),
                "role": "MASTER_TRADER",
                "display_name": "Alif Haikal (Master Operator)",
                "pin_hash": self._hash_pin(DEFAULT_MASTER_PIN),
                "pass_hash": None
            },
            DEFAULT_AUDITOR_USER: {
                "salt": secrets.token_hex(16),
                "role": "AUDITOR_VIEWER",
                "display_name": "Institutional Auditor",
                "pin_hash": self._hash_pin(DEFAULT_AUDITOR_PIN),
                "pass_hash": None
            }
        }
        # Compute hashes with their respective salts
        self._users[DEFAULT_MASTER_USER]["pass_hash"] = self._hash_password(DEFAULT_MASTER_PASS, self._users[DEFAULT_MASTER_USER]["salt"])
        self._users[DEFAULT_AUDITOR_USER]["pass_hash"] = self._hash_password(DEFAULT_AUDITOR_PASS, self._users[DEFAULT_AUDITOR_USER]["salt"])

    # -------------------------------------------------------------
    # Cryptographic Hash Utilities
    # -------------------------------------------------------------
    def _hash_password(self, password: str, salt: str) -> str:
        """Derives a cryptographic key using PBKDF2-HMAC-SHA256 with 100,000 rounds."""
        key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100000
        )
        return key.hex()

    def _hash_pin(self, pin: str) -> str:
        """Hashes 6-digit PIN with a static salt for rapid zero-latency lookup."""
        return hashlib.sha256(f"flowdev_pin_salt_{pin}".encode("utf-8")).hexdigest()

    # -------------------------------------------------------------
    # Rate Limiting & Lockout Defense
    # -------------------------------------------------------------
    def is_locked_out(self, client_id: str) -> Tuple[bool, int]:
        """Checks if a client identifier (user/IP) is temporarily locked out."""
        record = self._failed_attempts.get(client_id)
        if not record:
            return False, 0
        now = time.time()
        lockout_until = record.get("lockout_until", 0)
        if now < lockout_until:
            rem = int(lockout_until - now)
            return True, rem
        return False, 0

    def _record_failed_attempt(self, client_id: str):
        record = self._failed_attempts.setdefault(client_id, {"failed_count": 0, "lockout_until": 0})
        record["failed_count"] += 1
        if record["failed_count"] >= MAX_FAILED_ATTEMPTS:
            record["lockout_until"] = time.time() + LOCKOUT_DURATION_SEC
            record["failed_count"] = 0

    def _clear_failed_attempts(self, client_id: str):
        if client_id in self._failed_attempts:
            del self._failed_attempts[client_id]

    # -------------------------------------------------------------
    # Core Authentication Methods
    # -------------------------------------------------------------
    def authenticate_password(
        self,
        username: str,
        password: str,
        source: str = "WEB",
        client_id: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Authenticates an operator using username and cryptographic password."""
        cid = client_id or username
        locked, rem = self.is_locked_out(cid)
        if locked:
            self.db.record_auth_event(username, "UNKNOWN", "PASSWORD", source, "LOCKOUT", f"Cooldown: {rem}s")
            return False, f"Terlalu banyak percobaan gagal. Akun dikunci sementara selama {rem} detik.", None

        user_info = self._users.get(username)
        if not user_info:
            self._record_failed_attempt(cid)
            self.db.record_auth_event(username, "UNKNOWN", "PASSWORD", source, "FAILED", "Username tidak ditemukan")
            return False, "Username atau password salah.", None

        expected_hash = user_info["pass_hash"]
        actual_hash = self._hash_password(password, user_info["salt"])

        if hmac.compare_digest(expected_hash, actual_hash):
            self._clear_failed_attempts(cid)
            self.db.record_auth_event(username, user_info["role"], "PASSWORD", source, "SUCCESS", "Autentikasi password berhasil")
            token = self.create_session_token(username, user_info["role"])
            return True, "Login berhasil.", {
                "username": username,
                "role": user_info["role"],
                "display_name": user_info["display_name"],
                "token": token
            }
        else:
            self._record_failed_attempt(cid)
            self.db.record_auth_event(username, user_info["role"], "PASSWORD", source, "FAILED", "Password tidak cocok")
            return False, "Username atau password salah.", None

    def authenticate_pin(
        self,
        pin: str,
        source: str = "DESKTOP",
        client_id: str = "pin_auth"
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Authenticates using rapid 6-digit PIN."""
        locked, rem = self.is_locked_out(client_id)
        if locked:
            self.db.record_auth_event("PIN_OPERATOR", "UNKNOWN", "PIN", source, "LOCKOUT", f"Cooldown: {rem}s")
            return False, f"PIN terkunci sementara ({rem} detik tersisa).", None

        test_hash = self._hash_pin(pin.strip())
        for u_name, u_info in self._users.items():
            if hmac.compare_digest(u_info["pin_hash"], test_hash):
                self._clear_failed_attempts(client_id)
                self.db.record_auth_event(u_name, u_info["role"], "PIN", source, "SUCCESS", "PIN unlock berhasil")
                token = self.create_session_token(u_name, u_info["role"])
                return True, "PIN berhasil diverifikasi.", {
                    "username": u_name,
                    "role": u_info["role"],
                    "display_name": u_info["display_name"],
                    "token": token
                }

        self._record_failed_attempt(client_id)
        self.db.record_auth_event("UNKNOWN", "UNKNOWN", "PIN", source, "FAILED", "PIN salah")
        return False, "PIN tidak valid.", None

    def verify_cron_key(self, token: str) -> bool:
        """Validates automated background ping authorization from Cron-Job.org."""
        if not token:
            return False
        is_valid = hmac.compare_digest(DEFAULT_CRON_SECRET, token.strip())
        if is_valid:
            self.db.record_auth_event("CRON_ROBOT", "AUTOMATION", "CRON_KEY", "WEB", "SUCCESS", "Cron-Job.org keep-alive verified")
        else:
            self.db.record_auth_event("UNKNOWN_ROBOT", "UNKNOWN", "CRON_KEY", "WEB", "FAILED", "Invalid cron key")
        return is_valid

    # -------------------------------------------------------------
    # Session Token Management
    # -------------------------------------------------------------
    def create_session_token(self, username: str, role: str, valid_hours: int = 12) -> str:
        """Generates an HMAC-signed session token with expiration timestamp."""
        exp = int(time.time() + (valid_hours * 3600))
        payload = f"{username}|{role}|{exp}"
        signature = hmac.new(JWT_SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{payload}|{signature}"

    def verify_session_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validates session token authenticity and expiration."""
        try:
            parts = token.split("|")
            if len(parts) != 4:
                return None
            username, role, exp_str, signature = parts
            exp = int(exp_str)
            if time.time() > exp:
                return None  # expired
            payload = f"{username}|{role}|{exp_str}"
            expected_sig = hmac.new(JWT_SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected_sig, signature):
                u_info = self._users.get(username, {})
                return {
                    "username": username,
                    "role": role,
                    "display_name": u_info.get("display_name", username),
                    "token": token
                }
        except Exception:
            pass
        return None
