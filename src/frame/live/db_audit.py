"""
FLOWDEV FRAME - Unified Trade & Simulation Audit Database
Persistent SQLite database engine shared by both the Local Desktop Workstation
and the Cloud Web Application (Streamlit).
Records every live trade, Kinetic OMS stage upgrade, AI neural inference telemetry,
and historical simulation run with ACID compliance.
"""

import sqlite3, json, pathlib, time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import pandas as pd

DEFAULT_DB_PATH = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\data\flowdev_trade_audit.db")

class TradeAuditDB:
    def __init__(self, db_path: Optional[pathlib.Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cur = conn.cursor()
            
            # 1. Live Real-Time Trades Table
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
                    status TEXT NOT NULL, -- 'OPEN' or 'CLOSED'
                    source TEXT NOT NULL, -- 'DESKTOP' or 'CLOUD_STREAMLIT'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 2. Kinetic OMS Progression Log Table
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

            # 3. AI Neural Inference Telemetry Log Table
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

            # 4. Simulation / Backtest Audit Runs Table
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

            # 5. Security & Authentication Audit Log Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS auth_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    username TEXT NOT NULL,
                    role TEXT NOT NULL,
                    auth_method TEXT NOT NULL, -- 'PASSWORD', 'PIN', 'CRON_KEY', 'SESSION_RESTORE'
                    source TEXT NOT NULL,      -- 'WEB', 'DESKTOP'
                    status TEXT NOT NULL,      -- 'SUCCESS', 'FAILED', 'LOCKOUT'
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Indexes for ultra-fast query performance
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON live_trades(status);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_opentime ON live_trades(open_time);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_oms_trade ON oms_audit_log(trade_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_time ON ai_telemetry_log(timestamp_utc);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_auth_time ON auth_audit_log(timestamp_utc);")
            conn.commit()

    # -------------------------------------------------------------
    # Live Trade Operations
    # -------------------------------------------------------------
    def record_order_opened(self, pos: Dict[str, Any], source: str = "DESKTOP") -> bool:
        """Records an active open position into the database."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT OR REPLACE INTO live_trades (
                        trade_id, symbol, direction, lot_size, entry_price,
                        sl_dist, initial_sl, final_sl, tp_price, friction,
                        open_time, status, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
                """, (
                    pos.get("id"),
                    "XAUUSD",
                    pos.get("direction"),
                    pos.get("lot", 0.01),
                    pos.get("entry_price"),
                    pos.get("sl_dist"),
                    pos.get("initial_sl"),
                    pos.get("current_sl"),
                    pos.get("current_tp"),
                    pos.get("friction", 0.0),
                    pos.get("open_time", datetime.now(timezone.utc).isoformat()),
                    source
                ))
                conn.commit()
                return True
        except Exception as e:
            return False

    def record_order_closed(self, trade: Dict[str, Any]) -> bool:
        """Updates a trade record when it is closed with final exit metrics."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
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
                """, (
                    trade.get("exit_price"),
                    trade.get("final_sl", trade.get("exit_price")),
                    trade.get("net_pnl"),
                    trade.get("friction"),
                    trade.get("balance"),
                    trade.get("bars_held"),
                    trade.get("close_time", datetime.now(timezone.utc).isoformat()),
                    trade.get("exit_reason"),
                    trade.get("win", 1 if trade.get("net_pnl", 0) > 0 else 0),
                    trade.get("id")
                ))
                conn.commit()
                return True
        except Exception:
            return False

    def record_oms_event(self, trade_id: str, stage_name: str, details: str, sl_price: float):
        """Records a kinetic OMS escalation into the audit ledger."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                now_str = datetime.now(timezone.utc).isoformat()
                cur.execute("""
                    INSERT INTO oms_audit_log (trade_id, stage_name, details, sl_price, event_time)
                    VALUES (?, ?, ?, ?, ?)
                """, (trade_id, stage_name, details, sl_price, now_str))
                # Also update current SL on open trade
                cur.execute("UPDATE live_trades SET final_sl = ? WHERE trade_id = ?", (sl_price, trade_id))
                conn.commit()
        except Exception:
            pass

    def record_ai_telemetry(self, tele: Dict[str, Any], executed: bool = False, source: str = "DESKTOP"):
        """Records AI neural inference outputs for professional model monitoring."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO ai_telemetry_log (
                        timestamp_utc, session_name, action, conf_pct,
                        probs_json, atr, sl_dist, executed, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tele.get("time", datetime.now(timezone.utc).isoformat()),
                    tele.get("session", "OFF_SESSION"),
                    tele.get("action", "HOLD"),
                    tele.get("conf", 0.0),
                    json.dumps(tele.get("probs", [])),
                    tele.get("atr", 0.0),
                    tele.get("sl_dist", 0.0),
                    1 if executed else 0,
                    source
                ))
                conn.commit()
        except Exception:
            pass

    # -------------------------------------------------------------
    # Simulation / Backtest Audit Operations
    # -------------------------------------------------------------
    def record_simulation_run(self, results: Dict[str, Any]) -> int:
        """Stores a complete backtest audit run into the database."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO simulation_runs (
                        run_timestamp, period_mode, start_date, end_date,
                        initial_capital, final_equity, net_profit, return_pct,
                        win_rate, profit_factor, max_drawdown, total_trades,
                        sizing_mode, summary_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now(timezone.utc).isoformat(),
                    results.get("mode", "audit"),
                    results.get("start_date", ""),
                    results.get("end_date", ""),
                    results.get("initial_capital", 500.0),
                    results.get("final_equity", 500.0),
                    results.get("net_profit", 0.0),
                    results.get("return_pct", 0.0),
                    results.get("win_rate", 0.0),
                    results.get("profit_factor", 0.0),
                    results.get("max_drawdown", 0.0),
                    results.get("total_trades", 0),
                    results.get("sizing_mode", "flat"),
                    json.dumps({k: v for k, v in results.items() if k not in ("df_candles", "equity_curve", "equity_curve_flat", "equity_curve_dyn")})
                ))
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

    def get_active_order(self) -> Optional[Dict[str, Any]]:
        """Retrieves the single active trade currently open, if any."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM live_trades WHERE status = 'OPEN' ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            return dict(row) if row else None

    def get_oms_logs_for_trade(self, trade_id: str) -> List[Dict[str, Any]]:
        """Retrieves all kinetic OMS events for a specific trade."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM oms_audit_log WHERE trade_id = ? ORDER BY id ASC", (trade_id,))
            return [dict(r) for r in cur.fetchall()]

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
            tot = r["total_trades"] or 0
            wins = r["wins"] or 0
            losses = r["losses"] or 0
            pnl = r["total_pnl"] or 0.0
            gp = r["gross_profit"] or 0.0
            gl = r["gross_loss"] or 0.0
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
        """
        Builds a comprehensive audit evaluation package from closed live trades,
        matching the exact structure and visual fidelity of the historical backtest report.
        """
        with self._get_connection() as conn:
            query = "SELECT * FROM live_trades WHERE status = 'CLOSED'"
            params = []
            if start_date:
                query += " AND open_time >= ?"
                params.append(start_date)
            if end_date:
                query += " AND open_time <= ?"
                params.append(end_date)
            query += " ORDER BY id ASC"
            
            df = pd.read_sql_query(query, conn, params=params)

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
