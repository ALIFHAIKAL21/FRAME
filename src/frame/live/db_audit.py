"""
FLOWDEV FRAME - Unified Trade & Simulation Audit Database
Dual-Driver Database Engine:
- Primary: Neon Serverless Cloud PostgreSQL (Shared Real-Time Persistence 24/7)
- Fallback: Local SQLite database (ACID offline fallback)
Ensures 100% synchronization between Desktop Workstation and 24/7 Cloud Server.
"""

import os, sqlite3, json, pathlib, time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import pandas as pd

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

_ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_SQLITE_PATH = _ROOT_DIR / "data" / "flowdev_trade_audit.db"
DEFAULT_NEON_URL = "postgresql://neondb_owner:npg_RguYVSxW2El4@ep-morning-bread-b59ipjyn-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require"

class SafeConnectionWrapper:
    """Auto-committing and auto-closing connection wrapper for PostgreSQL and SQLite."""
    def __init__(self, conn, is_postgres=False):
        self._conn = conn
        self.is_postgres = is_postgres

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        except Exception:
            pass
        finally:
            try:
                self._conn.close()
            except Exception:
                pass

class TradeAuditDB:
    def __init__(self, db_path: Optional[pathlib.Path] = None, database_url: Optional[str] = None):
        self.db_path = db_path or DEFAULT_SQLITE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_url = database_url or os.environ.get("DATABASE_URL") or DEFAULT_NEON_URL
        self.is_postgres = False

        # Attempt PostgreSQL connection
        if HAS_PSYCOPG2 and self.database_url:
            try:
                conn = psycopg2.connect(self.database_url, connect_timeout=5)
                conn.close()
                self.is_postgres = True
            except Exception as e:
                print(f"[DB] Neon PostgreSQL connection failed ({e}), falling back to SQLite.")
                self.is_postgres = False

        self._init_db()

    def _get_connection(self):
        if self.is_postgres:
            conn = psycopg2.connect(self.database_url, cursor_factory=psycopg2.extras.RealDictCursor)
            return SafeConnectionWrapper(conn, is_postgres=True)
        else:
            conn = sqlite3.connect(str(self.db_path), timeout=15.0)
            conn.row_factory = sqlite3.Row
            return SafeConnectionWrapper(conn, is_postgres=False)

    def _init_db(self):
        with self._get_connection() as conn:
            cur = conn.cursor()
            if self.is_postgres:
                # 1. PostgreSQL Schema
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS live_trades (
                        id SERIAL PRIMARY KEY,
                        trade_id VARCHAR(64) UNIQUE NOT NULL,
                        symbol VARCHAR(32) NOT NULL DEFAULT 'XAUUSD',
                        direction VARCHAR(16) NOT NULL,
                        lot_size DOUBLE PRECISION NOT NULL DEFAULT 0.01,
                        entry_price DOUBLE PRECISION NOT NULL,
                        exit_price DOUBLE PRECISION,
                        sl_dist DOUBLE PRECISION NOT NULL,
                        initial_sl DOUBLE PRECISION,
                        final_sl DOUBLE PRECISION,
                        tp_price DOUBLE PRECISION,
                        net_pnl DOUBLE PRECISION,
                        friction DOUBLE PRECISION,
                        balance_after DOUBLE PRECISION,
                        bars_held INTEGER DEFAULT 0,
                        open_time TEXT NOT NULL,
                        close_time TEXT,
                        exit_reason TEXT,
                        win_flag INTEGER,
                        status VARCHAR(16) NOT NULL DEFAULT 'OPEN',
                        source VARCHAR(64) NOT NULL DEFAULT 'DESKTOP',
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oms_audit_log (
                        id SERIAL PRIMARY KEY,
                        trade_id VARCHAR(64) NOT NULL,
                        stage_name VARCHAR(64) NOT NULL,
                        details TEXT NOT NULL,
                        sl_price DOUBLE PRECISION NOT NULL,
                        event_time TEXT NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ai_telemetry_log (
                        id SERIAL PRIMARY KEY,
                        timestamp_utc TEXT NOT NULL,
                        session_name VARCHAR(64) NOT NULL,
                        action VARCHAR(16) NOT NULL,
                        conf_pct DOUBLE PRECISION NOT NULL,
                        probs_json TEXT,
                        atr DOUBLE PRECISION,
                        sl_dist DOUBLE PRECISION,
                        executed INTEGER DEFAULT 0,
                        source VARCHAR(64) NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS simulation_runs (
                        id SERIAL PRIMARY KEY,
                        run_timestamp TEXT NOT NULL,
                        period_mode VARCHAR(64) NOT NULL,
                        start_date TEXT,
                        end_date TEXT,
                        initial_capital DOUBLE PRECISION NOT NULL,
                        final_equity DOUBLE PRECISION NOT NULL,
                        net_profit DOUBLE PRECISION NOT NULL,
                        return_pct DOUBLE PRECISION NOT NULL,
                        win_rate DOUBLE PRECISION NOT NULL,
                        profit_factor DOUBLE PRECISION NOT NULL,
                        max_drawdown DOUBLE PRECISION NOT NULL,
                        total_trades INTEGER NOT NULL,
                        sizing_mode VARCHAR(32) NOT NULL,
                        summary_json TEXT,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS auth_audit_log (
                        id SERIAL PRIMARY KEY,
                        timestamp_utc TEXT NOT NULL,
                        username VARCHAR(64) NOT NULL,
                        role VARCHAR(32) NOT NULL,
                        auth_method VARCHAR(32) NOT NULL,
                        source VARCHAR(32) NOT NULL,
                        status VARCHAR(32) NOT NULL,
                        details TEXT,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS operational_state (
                        id SERIAL PRIMARY KEY,
                        state_key VARCHAR(64) UNIQUE NOT NULL,
                        state_json TEXT NOT NULL,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON live_trades(status);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_opentime ON live_trades(open_time);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_oms_trade ON oms_audit_log(trade_id);")
            else:
                # 2. SQLite Schema Fallback
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS live_trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        trade_id TEXT UNIQUE NOT NULL,
                        symbol TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        lot_size REAL NOT NULL,
                        entry_price REAL NOT NULL,
                        exit_price REAL,
                        sl_dist REAL NOT NULL,
                        initial_sl REAL,
                        final_sl REAL,
                        tp_price REAL,
                        net_pnl REAL,
                        friction REAL,
                        balance_after REAL,
                        bars_held INTEGER,
                        open_time TEXT NOT NULL,
                        close_time TEXT,
                        exit_reason TEXT,
                        win_flag INTEGER,
                        status TEXT NOT NULL,
                        source TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oms_audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        trade_id TEXT NOT NULL,
                        stage_name TEXT NOT NULL,
                        details TEXT NOT NULL,
                        sl_price REAL NOT NULL,
                        event_time TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ai_telemetry_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp_utc TEXT NOT NULL,
                        session_name TEXT NOT NULL,
                        action TEXT NOT NULL,
                        conf_pct REAL NOT NULL,
                        probs_json TEXT,
                        atr REAL,
                        sl_dist REAL,
                        executed INTEGER DEFAULT 0,
                        source TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS simulation_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_timestamp TEXT NOT NULL,
                        period_mode TEXT NOT NULL,
                        start_date TEXT,
                        end_date TEXT,
                        initial_capital REAL NOT NULL,
                        final_equity REAL NOT NULL,
                        net_profit REAL NOT NULL,
                        return_pct REAL NOT NULL,
                        win_rate REAL NOT NULL,
                        profit_factor REAL NOT NULL,
                        max_drawdown REAL NOT NULL,
                        total_trades INTEGER NOT NULL,
                        sizing_mode TEXT NOT NULL,
                        summary_json TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS auth_audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp_utc TEXT NOT NULL,
                        username TEXT NOT NULL,
                        role TEXT NOT NULL,
                        auth_method TEXT NOT NULL,
                        source TEXT NOT NULL,
                        status TEXT NOT NULL,
                        details TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS operational_state (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        state_key TEXT UNIQUE NOT NULL,
                        state_json TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON live_trades(status);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_opentime ON live_trades(open_time);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_oms_trade ON oms_audit_log(trade_id);")

            conn.commit()

    # -------------------------------------------------------------
    # Shared Operational State Operations (Zero Desynchronization)
    # -------------------------------------------------------------
    def save_operational_state(self, state_data: Dict[str, Any], state_key: str = "GLOBAL_STATE") -> bool:
        """Saves operational state to Neon PostgreSQL (or SQLite)."""
        try:
            state_str = json.dumps(state_data, default=str)
            with self._get_connection() as conn:
                cur = conn.cursor()
                if self.is_postgres:
                    cur.execute("""
                        INSERT INTO operational_state (state_key, state_json, updated_at)
                        VALUES (%s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (state_key) DO UPDATE SET
                            state_json = EXCLUDED.state_json,
                            updated_at = CURRENT_TIMESTAMP
                    """, (state_key, state_str))
                else:
                    cur.execute("""
                        INSERT OR REPLACE INTO operational_state (state_key, state_json, updated_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                    """, (state_key, state_str))
                conn.commit()
                return True
        except Exception as e:
            print(f"[DB Save State Error] {e}")
            return False

    def get_operational_state(self, state_key: str = "GLOBAL_STATE") -> Optional[Dict[str, Any]]:
        """Retrieves latest operational state from Neon PostgreSQL (or SQLite)."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                if self.is_postgres:
                    cur.execute("SELECT state_json FROM operational_state WHERE state_key = %s", (state_key,))
                else:
                    cur.execute("SELECT state_json FROM operational_state WHERE state_key = ?", (state_key,))
                row = cur.fetchone()
                if row:
                    val = row["state_json"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[0]
                    return json.loads(val)
        except Exception as e:
            print(f"[DB Get State Error] {e}")
        return None

    # -------------------------------------------------------------
    # Live Trade Operations
    # -------------------------------------------------------------
    def record_order_opened(self, pos: Dict[str, Any], source: str = "DESKTOP") -> bool:
        """Records an active open position into the database."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                trade_id = pos.get("id") or pos.get("trade_id")
                sym = pos.get("symbol", "XAUUSD")
                d = pos.get("direction", "BUY")
                lot = float(pos.get("lot", 0.01))
                ep = float(pos.get("entry_price", 0.0))
                sl_d = float(pos.get("sl_dist", 0.0))
                init_sl = float(pos.get("initial_sl", 0.0)) if pos.get("initial_sl") else ep
                fin_sl = float(pos.get("current_sl", init_sl))
                tp = float(pos.get("current_tp", 0.0)) if pos.get("current_tp") else None
                fric = float(pos.get("friction", 0.0))
                op_t = str(pos.get("open_time") or datetime.now(timezone.utc).isoformat())

                if self.is_postgres:
                    cur.execute("""
                        INSERT INTO live_trades (
                            trade_id, symbol, direction, lot_size, entry_price,
                            sl_dist, initial_sl, final_sl, tp_price, friction,
                            open_time, status, source
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'OPEN', %s)
                        ON CONFLICT (trade_id) DO UPDATE SET
                            symbol = EXCLUDED.symbol,
                            direction = EXCLUDED.direction,
                            lot_size = EXCLUDED.lot_size,
                            entry_price = EXCLUDED.entry_price,
                            sl_dist = EXCLUDED.sl_dist,
                            initial_sl = EXCLUDED.initial_sl,
                            final_sl = EXCLUDED.final_sl,
                            tp_price = EXCLUDED.tp_price,
                            friction = EXCLUDED.friction,
                            open_time = EXCLUDED.open_time,
                            status = 'OPEN',
                            source = EXCLUDED.source
                    """, (trade_id, sym, d, lot, ep, sl_d, init_sl, fin_sl, tp, fric, op_t, source))
                else:
                    cur.execute("""
                        INSERT OR REPLACE INTO live_trades (
                            trade_id, symbol, direction, lot_size, entry_price,
                            sl_dist, initial_sl, final_sl, tp_price, friction,
                            open_time, status, source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
                    """, (trade_id, sym, d, lot, ep, sl_d, init_sl, fin_sl, tp, fric, op_t, source))
                conn.commit()
                return True
        except Exception as e:
            print(f"[DB Record Order Open Error] {e}")
            return False

    def record_order_closed(self, trade: Dict[str, Any]) -> bool:
        """Updates a trade record when it is closed with final exit metrics."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                ep_exit = float(trade.get("exit_price", 0.0))
                fin_sl = float(trade.get("final_sl", ep_exit))
                net_p = float(trade.get("net_pnl", 0.0))
                fric = float(trade.get("friction", 0.0))
                bal = float(trade.get("balance", 0.0)) if trade.get("balance") else None
                bars = int(trade.get("bars_held", 1))
                cl_time = str(trade.get("close_time") or datetime.now(timezone.utc).isoformat())
                reason = str(trade.get("exit_reason", "Closed"))
                win = 1 if net_p > 0 else 0
                tid = trade.get("id") or trade.get("trade_id")

                if self.is_postgres:
                    cur.execute("""
                        UPDATE live_trades SET
                            exit_price = %s,
                            final_sl = %s,
                            net_pnl = %s,
                            friction = %s,
                            balance_after = %s,
                            bars_held = %s,
                            close_time = %s,
                            exit_reason = %s,
                            win_flag = %s,
                            status = 'CLOSED'
                        WHERE trade_id = %s
                    """, (ep_exit, fin_sl, net_p, fric, bal, bars, cl_time, reason, win, tid))
                else:
                    cur.execute("""
                        UPDATE live_trades SET
                            exit_price = ?,
                            final_sl = ?,
                            net_pnl = ?,
                            friction = ?,
                            balance_after = ?,
                            bars_held = ?,
                            close_time = ?,
                            exit_reason = ?,
                            win_flag = ?,
                            status = 'CLOSED'
                        WHERE trade_id = ?
                    """, (ep_exit, fin_sl, net_p, fric, bal, bars, cl_time, reason, win, tid))
                conn.commit()
                return True
        except Exception as e:
            print(f"[DB Record Order Close Error] {e}")
            return False

    def record_oms_event(self, trade_id: str, stage_name: str, details: str, sl_price: float):
        """Records a kinetic OMS escalation into the audit ledger."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                now_str = datetime.now(timezone.utc).isoformat()
                if self.is_postgres:
                    cur.execute("""
                        INSERT INTO oms_audit_log (trade_id, stage_name, details, sl_price, event_time)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (trade_id, stage_name, details, sl_price, now_str))
                    cur.execute("UPDATE live_trades SET final_sl = %s WHERE trade_id = %s", (sl_price, trade_id))
                else:
                    cur.execute("""
                        INSERT INTO oms_audit_log (trade_id, stage_name, details, sl_price, event_time)
                        VALUES (?, ?, ?, ?, ?)
                    """, (trade_id, stage_name, details, sl_price, now_str))
                    cur.execute("UPDATE live_trades SET final_sl = ? WHERE trade_id = ?", (sl_price, trade_id))
                conn.commit()
        except Exception as e:
            print(f"[DB Record OMS Error] {e}")

    def record_ai_telemetry(self, tele: Dict[str, Any], executed: bool = False, source: str = "DESKTOP"):
        """Records AI neural inference outputs for professional model monitoring."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                t_utc = tele.get("time", datetime.now(timezone.utc).isoformat())
                sess = tele.get("session", "OFF_SESSION")
                act = tele.get("action", "HOLD")
                conf = float(tele.get("conf", 0.0))
                pj = json.dumps(tele.get("probs", []))
                atr = float(tele.get("atr", 0.0))
                sld = float(tele.get("sl_dist", 0.0))
                ex = 1 if executed else 0

                if self.is_postgres:
                    cur.execute("""
                        INSERT INTO ai_telemetry_log (
                            timestamp_utc, session_name, action, conf_pct,
                            probs_json, atr, sl_dist, executed, source
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (t_utc, sess, act, conf, pj, atr, sld, ex, source))
                else:
                    cur.execute("""
                        INSERT INTO ai_telemetry_log (
                            timestamp_utc, session_name, action, conf_pct,
                            probs_json, atr, sl_dist, executed, source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (t_utc, sess, act, conf, pj, atr, sld, ex, source))
                conn.commit()
        except Exception:
            pass

    def record_simulation_run(self, results: Dict[str, Any]) -> int:
        """Stores a complete backtest audit run into the database."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                now_str = datetime.now(timezone.utc).isoformat()
                m = results.get("mode", "audit")
                sd = results.get("start_date", "")
                ed = results.get("end_date", "")
                ic = float(results.get("initial_capital", 500.0))
                fe = float(results.get("final_equity", 500.0))
                np_val = float(results.get("net_profit", 0.0))
                rp = float(results.get("return_pct", 0.0))
                wr = float(results.get("win_rate", 0.0))
                pf = float(results.get("profit_factor", 0.0))
                mdd = float(results.get("max_drawdown", 0.0))
                tt = int(results.get("total_trades", 0))
                sm = results.get("sizing_mode", "flat")
                sum_j = json.dumps({k: v for k, v in results.items() if k not in ("df_candles", "equity_curve", "equity_curve_flat", "equity_curve_dyn")})

                if self.is_postgres:
                    cur.execute("""
                        INSERT INTO simulation_runs (
                            run_timestamp, period_mode, start_date, end_date,
                            initial_capital, final_equity, net_profit, return_pct,
                            win_rate, profit_factor, max_drawdown, total_trades,
                            sizing_mode, summary_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (now_str, m, sd, ed, ic, fe, np_val, rp, wr, pf, mdd, tt, sm, sum_j))
                    row = cur.fetchone()
                    conn.commit()
                    return row["id"] if row else 1
                else:
                    cur.execute("""
                        INSERT INTO simulation_runs (
                            run_timestamp, period_mode, start_date, end_date,
                            initial_capital, final_equity, net_profit, return_pct,
                            win_rate, profit_factor, max_drawdown, total_trades,
                            sizing_mode, summary_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (now_str, m, sd, ed, ic, fe, np_val, rp, wr, pf, mdd, tt, sm, sum_j))
                    conn.commit()
                    return cur.lastrowid
        except Exception:
            return -1

    # -------------------------------------------------------------
    # Query & Analytics Operations
    # -------------------------------------------------------------
    def get_closed_trades_df(self, limit: int = 100) -> pd.DataFrame:
        """Retrieves closed trades as a pandas DataFrame for reporting."""
        with self._get_connection() as conn:
            query = f"SELECT * FROM live_trades WHERE status = 'CLOSED' ORDER BY id DESC LIMIT {int(limit)}"
            return pd.read_sql_query(query, conn)

    def get_all_trades_df(self, limit: int = 200) -> pd.DataFrame:
        """Retrieves both open and closed trades."""
        with self._get_connection() as conn:
            query = f"SELECT * FROM live_trades ORDER BY id DESC LIMIT {int(limit)}"
            return pd.read_sql_query(query, conn)

    def get_active_order(self) -> Optional[Dict[str, Any]]:
        """Retrieves the single active trade currently open, if any."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM live_trades WHERE status = 'OPEN' ORDER BY id DESC LIMIT 1")
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            print(f"[DB Get Active Order Error] {e}")
            return None

    def get_oms_logs_for_trade(self, trade_id: str) -> List[Dict[str, Any]]:
        """Retrieves all kinetic OMS events for a specific trade."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                if self.is_postgres:
                    cur.execute("SELECT * FROM oms_audit_log WHERE trade_id = %s ORDER BY id ASC", (trade_id,))
                else:
                    cur.execute("SELECT * FROM oms_audit_log WHERE trade_id = ? ORDER BY id ASC", (trade_id,))
                return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []

    def get_recent_telemetry_df(self, limit: int = 50) -> pd.DataFrame:
        """Retrieves recent AI inference logs."""
        with self._get_connection() as conn:
            return pd.read_sql_query(f"SELECT * FROM ai_telemetry_log ORDER BY id DESC LIMIT {int(limit)}", conn)

    def get_simulation_runs_df(self, limit: int = 20) -> pd.DataFrame:
        """Retrieves historical backtest audit runs."""
        with self._get_connection() as conn:
            return pd.read_sql_query(f"SELECT * FROM simulation_runs ORDER BY id DESC LIMIT {int(limit)}", conn)

    def record_auth_event(
        self,
        username: str,
        role: str,
        auth_method: str,
        source: str,
        status: str,
        details: str = ""
    ) -> bool:
        """Records an authentication / login event into the security audit ledger."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                now_str = datetime.now(timezone.utc).isoformat()
                if self.is_postgres:
                    cur.execute("""
                        INSERT INTO auth_audit_log (
                            timestamp_utc, username, role, auth_method, source, status, details
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (now_str, username, role, auth_method, source, status, details))
                else:
                    cur.execute("""
                        INSERT INTO auth_audit_log (
                            timestamp_utc, username, role, auth_method, source, status, details
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (now_str, username, role, auth_method, source, status, details))
                conn.commit()
                return True
        except Exception:
            return False

    def get_auth_logs_df(self, limit: int = 50) -> pd.DataFrame:
        """Retrieves recent security access and login events."""
        with self._get_connection() as conn:
            return pd.read_sql_query(
                f"SELECT * FROM auth_audit_log ORDER BY id DESC LIMIT {int(limit)}", conn
            )

    def get_overall_stats(self) -> Dict[str, Any]:
        """Calculates live trading performance metrics from database."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN win_flag = 1 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN win_flag = 0 THEN 1 ELSE 0 END) as losses,
                    COALESCE(SUM(net_pnl), 0.0) as total_pnl,
                    COALESCE(SUM(CASE WHEN net_pnl > 0 THEN net_pnl ELSE 0 END), 0.0) as gross_profit,
                    COALESCE(SUM(CASE WHEN net_pnl < 0 THEN ABS(net_pnl) ELSE 0 END), 0.0) as gross_loss
                FROM live_trades WHERE status = 'CLOSED'
            """)
            r = cur.fetchone()
            tot = (r["total_trades"] if isinstance(r, dict) or hasattr(r, "__getitem__") else r[0]) or 0
            wins = (r["wins"] if isinstance(r, dict) or hasattr(r, "__getitem__") else r[1]) or 0
            losses = (r["losses"] if isinstance(r, dict) or hasattr(r, "__getitem__") else r[2]) or 0
            pnl = (r["total_pnl"] if isinstance(r, dict) or hasattr(r, "__getitem__") else r[3]) or 0.0
            gp = (r["gross_profit"] if isinstance(r, dict) or hasattr(r, "__getitem__") else r[4]) or 0.0
            gl = (r["gross_loss"] if isinstance(r, dict) or hasattr(r, "__getitem__") else r[5]) or 0.0
            wr = (wins / tot * 100) if tot > 0 else 0.0
            pf = (gp / gl) if gl > 0 else (999.0 if gp > 0 else 0.0)
            return {
                "total_trades": tot,
                "wins": wins,
                "losses": losses,
                "win_rate": round(wr, 1),
                "profit_factor": round(pf, 2),
                "net_profit": round(pnl, 2)
            }

    def get_live_trades_evaluation(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_capital: float = 500.0
    ) -> Dict[str, Any]:
        """Builds a comprehensive audit evaluation package from closed live trades."""
        with self._get_connection() as conn:
            query = "SELECT * FROM live_trades WHERE status = 'CLOSED'"
            params = []
            param_placeholder = "%s" if self.is_postgres else "?"
            if start_date:
                query += f" AND open_time >= {param_placeholder}"
                params.append(start_date)
            if end_date:
                query += f" AND open_time <= {param_placeholder}"
                params.append(end_date)
            query += " ORDER BY id ASC"
            
            df = pd.read_sql_query(query, conn, params=tuple(params) if params else None)

        if df.empty:
            return {
                "has_data": False,
                "initial_capital": initial_capital,
                "final_equity": initial_capital,
                "net_pnl": 0.0,
                "return_pct": 0.0,
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "max_drawdown": 0.0,
                "equity_curve": [initial_capital],
                "equity_dates": [datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")],
                "trades": [],
                "monthly": [],
                "oms_breakdown": {}
            }

        trades_list = []
        equity_curve = [initial_capital]
        equity_dates = [df.iloc[0]["open_time"][:16]]
        running_cash = initial_capital
        peak_cash = initial_capital
        max_dd = 0.0

        for _, row in df.iterrows():
            pnl = float(row["net_pnl"])
            running_cash += pnl
            equity_curve.append(round(running_cash, 2))
            equity_dates.append(str(row["close_time"])[:16])

            if running_cash > peak_cash:
                peak_cash = running_cash
            dd = ((peak_cash - running_cash) / peak_cash * 100) if peak_cash > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

            trades_list.append({
                "id": row["trade_id"],
                "entry_time": str(row["open_time"])[:16],
                "exit_time": str(row["close_time"])[:16],
                "direction": row["direction"],
                "lots": float(row["lot_size"]),
                "entry": float(row["entry_price"]),
                "exit": float(row["exit_price"]),
                "sl": float(row["final_sl"]) if row["final_sl"] else float(row["initial_sl"]),
                "pnl": pnl,
                "balance": round(running_cash, 2),
                "bars_held": int(row["bars_held"]) if row["bars_held"] else 1,
                "exit_reason": row["exit_reason"] or "Closed",
                "win": int(row["win_flag"])
            })

        n_trades = len(trades_list)
        wins = [t for t in trades_list if t["win"] == 1]
        losses = [t for t in trades_list if t["win"] == 0]
        wr = (len(wins) / n_trades * 100) if n_trades > 0 else 0.0
        tot_win = sum(t["pnl"] for t in wins)
        tot_loss = abs(sum(t["pnl"] for t in losses))
        pf = (tot_win / tot_loss) if tot_loss > 0 else (999.0 if tot_win > 0 else 0.0)
        net_pnl = running_cash - initial_capital
        ret_pct = (net_pnl / initial_capital) * 100

        # Monthly aggregation
        df["month"] = pd.to_datetime(df["close_time"], errors="coerce").dt.strftime("%Y-%m")
        monthly = []
        if "month" in df.columns:
            for m_name, grp in df.groupby("month"):
                m_wins = int(grp["win_flag"].sum())
                m_tot = len(grp)
                m_loss = m_tot - m_wins
                m_pnl = float(grp["net_pnl"].sum())
                monthly.append({
                    "month": str(m_name),
                    "trades": m_tot,
                    "wins": m_wins,
                    "losses": m_loss,
                    "win_rate": round((m_wins / m_tot * 100), 1) if m_tot > 0 else 0.0,
                    "pnl": round(m_pnl, 2),
                    "balance": round(initial_capital + float(df[df['close_time'] <= grp['close_time'].max()]['net_pnl'].sum()), 2)
                })

        # Kinetic OMS breakdown
        oms_counts = df["exit_reason"].value_counts().to_dict()

        return {
            "has_data": True,
            "mode": f"Live Trades Audit ({start_date or 'Earliest'} to {end_date or 'Latest'})",
            "initial_capital": initial_capital,
            "final_equity": round(running_cash, 2),
            "net_pnl": round(net_pnl, 2),
            "return_pct": round(ret_pct, 2),
            "total_trades": n_trades,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(wr, 2),
            "profit_factor": round(pf, 2),
            "max_drawdown": round(max_dd, 2),
            "equity_curve": equity_curve,
            "equity_dates": equity_dates,
            "trades": list(reversed(trades_list)),
            "monthly": monthly,
            "oms_breakdown": oms_counts
        }
