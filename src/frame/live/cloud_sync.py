"""
FLOWDEV FRAME - Cloud State Synchronization Engine
Facilitates seamless real-time state sharing between the 24/7 Cloud Web Worker (Streamlit)
and the Local Desktop Workstation.
Supports free cloud key-value stores (JSONBin.io, Upstash, Supabase, GitHub Gist)
with local file fallback (logs/cloud_shared_state.json).
"""

import os, json, time, pathlib, urllib.request, urllib.parse
from datetime import datetime, timezone
from typing import Optional, Dict, Any

STATE_FILE_PATH = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\logs\cloud_shared_state.json")

class CloudStateSync:
    def __init__(self, api_endpoint: Optional[str] = None, api_key: Optional[str] = None):
        self.api_endpoint = api_endpoint or os.environ.get("CLOUD_SYNC_URL", "").strip()
        self.api_key = api_key or os.environ.get("CLOUD_SYNC_KEY", "").strip()
        self.local_file = STATE_FILE_PATH
        self.local_file.parent.mkdir(parents=True, exist_ok=True)

    def is_cloud_configured(self) -> bool:
        return bool(self.api_endpoint and len(self.api_endpoint) > 8)

    def push_state(self, state: Dict[str, Any]) -> bool:
        """Pushes current live trading state to cloud and/or local shared file."""
        state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        state["timestamp_epoch"] = time.time()

        # 1. Save to local state file always
        try:
            with open(self.local_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
        except Exception:
            pass

        # 2. Push to Cloud Store if configured
        if self.is_cloud_configured():
            try:
                data_bytes = json.dumps(state).encode("utf-8")
                headers = {"Content-Type": "application/json", "User-Agent": "FlowdevFrame/1.0"}
                if self.api_key:
                    headers["X-Master-Key"] = self.api_key
                    headers["Authorization"] = f"Bearer {self.api_key}"

                req = urllib.request.Request(self.api_endpoint, data=data_bytes, headers=headers, method="PUT")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return resp.status in (200, 201)
            except Exception:
                return False

        return True

    def pull_state(self) -> Optional[Dict[str, Any]]:
        """Pulls latest trading state from cloud (or local file fallback)."""
        # 1. Try Cloud Store first if configured
        if self.is_cloud_configured():
            try:
                headers = {"User-Agent": "FlowdevFrame/1.0"}
                if self.api_key:
                    headers["X-Master-Key"] = self.api_key
                    headers["Authorization"] = f"Bearer {self.api_key}"
                req = urllib.request.Request(self.api_endpoint, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        raw = resp.read().decode("utf-8")
                        data = json.loads(raw)
                        # Handle JSONBin structure if wrapped in 'record'
                        if isinstance(data, dict) and "record" in data:
                            return data["record"]
                        return data
            except Exception:
                pass

        # 2. Fallback to local shared state file
        if self.local_file.exists():
            try:
                with open(self.local_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        return None

    def send_command(self, cmd_type: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        """Sends an action command (e.g. PANIC_CLOSE, PAUSE, RESUME) from Desktop/Mobile."""
        current_state = self.pull_state() or {}
        commands = current_state.get("pending_commands", [])
        commands.append({
            "id": f"cmd-{int(time.time()*1000)}",
            "type": cmd_type,
            "payload": payload or {},
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "executed": False
        })
        current_state["pending_commands"] = commands[-10:] # keep last 10
        return self.push_state(current_state)

    def pop_commands(self) -> list:
        """Pulls and clears unexecuted commands (used by Cloud Worker)."""
        current_state = self.pull_state() or {}
        commands = current_state.get("pending_commands", [])
        unexecuted = [c for c in commands if not c.get("executed", False)]
        if unexecuted:
            for c in commands:
                c["executed"] = True
            current_state["pending_commands"] = commands
            self.push_state(current_state)
        return unexecuted
