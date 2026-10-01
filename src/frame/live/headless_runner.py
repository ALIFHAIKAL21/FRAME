"""
FLOWDEV FRAME - Headless 24/7 Live Paper Trader Runner
Runs continuously in background / VPS / Cloud Server without needing a desktop display.
Monitors XAU/USD M30 ticks, executes LoRA PyTorch inference on candle completion,
drives 4-stage Kinetic OMS, updates state JSON, and sends alerts to Telegram.
"""

import sys, pathlib, time, signal, json
from datetime import datetime, timezone

try:
    from PySide6.QtCore import QCoreApplication, QTimer
except ImportError:
    from PyQt6.QtCore import QCoreApplication, QTimer

from src.frame.banner import print_frame_banner
from .paper_broker import LivePaperBroker
from .feed import LiveMarketFeed
from .agent import LiveAgent
from .telegram_bot import LiveTelegramNotifier
from .db_audit import TradeAuditDB

class HeadlessLiveTrader:
    def __init__(self, initial_capital: float = 250.0, lot_mode: str = "dynamic", max_lot: float = 0.02):
        self.app = QCoreApplication.instance() or QCoreApplication(sys.argv)
        
        # Engines
        self.broker = LivePaperBroker(initial_capital=initial_capital, lot_mode=lot_mode, max_lot=max_lot, session_id="MOMENT_LOCKED_PROD")
        self.feed = LiveMarketFeed(symbol="XAUUSD", poll_interval_ms=250)
        self.agent = LiveAgent(broker=self.broker, session_id="MOMENT_LOCKED_PROD", session_name="MOMENT-1-large (Locked Production)")
        self.telegram = LiveTelegramNotifier()
        self.db = TradeAuditDB()

        # State output
        self.state_file = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\data\cloud_trader_state.json")
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        self._wire_signals()

        # Periodic status logger (every 30 seconds)
        self.log_timer = QTimer()
        self.log_timer.timeout.connect(self._log_heartbeat)
        self.log_timer.start(30000)

    def _wire_signals(self):
        # Feed -> Agent & Broker
        self.feed.tick_received.connect(self.agent.on_tick)
        self.feed.m30_candle_closed.connect(self._on_m30_candle_closed)
        self.feed.connection_changed.connect(self._on_connection_changed)

        # Agent -> Events
        self.agent.order_opened.connect(self._on_order_opened)
        self.agent.order_closed.connect(self._on_order_closed)
        self.agent.oms_event.connect(self._on_oms_event)
        self.agent.telemetry_updated.connect(self._on_telemetry)

    def _on_connection_changed(self, connected: bool, source: str, msg: str):
        status_tag = "[CONNECTED]" if connected else "[DISCONNECTED]"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {status_tag} Feed Source: {source} | {msg}")

    def _on_m30_candle_closed(self, candle: dict):
        self.agent.on_candle_closed(candle, self.feed.get_m30_history())


    def _on_order_opened(self, pos: dict):
        d = pos.get('direction')
        ep = pos.get('entry_price')
        lot = pos.get('lot')
        sl = pos.get('current_sl')
        tp = pos.get('current_tp')
        print(f"\n>>> [EXECUTION] NEW ORDER: {d} {lot:.2f} Lot @ ${ep:.2f} | SL: ${sl:.2f} | TP: ${tp:.2f} (+2.7R) <<<")
        self.telegram.notify_order_opened(pos, self.broker.cash)
        if self.db is not None:
            self.db.record_order_opened(pos, source="MOMENT_LOCKED_PROD")
        self._save_state()

    def _on_order_closed(self, trade: dict):
        pnl = trade.get('net_pnl', 0.0)
        reason = trade.get('exit_reason', 'Closed')
        print(f"\n>>> [CLOSED] {trade.get('direction')} closed @ ${trade.get('exit_price', 0.0):.2f} | Net PnL: {'+' if pnl>=0 else ''}${pnl:.2f} ({reason}) <<<")
        if self.db is not None:
            self.db.record_order_closed(trade)
        stats = self.broker.get_stats()
        self.telegram.notify_order_closed(trade, stats)
        self._save_state()

    def _on_oms_event(self, stage: str, details: str, sl: float):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [KINETIC OMS] {stage}: {details} (New SL: ${sl:.2f})")
        if self.db is not None:
            trade_id = self.broker.open_position.get("id", "") if self.broker.open_position else ""
            self.db.record_oms_event(trade_id, stage, details, sl)
        self.telegram.notify_oms_event(stage, details, sl)
        self._save_state()

    def _on_telemetry(self, tele: dict):
        action = tele.get('action')
        conf = tele.get('conf')
        session = tele.get('session')
        if action != "HOLD":
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [AI TELEMETRY] Session: {session} | Signal: {action} ({conf:.1f}%)")
            if self.db is not None:
                self.db.record_ai_telemetry(tele, executed=True, source="MOMENT_LOCKED_PROD")

    def _log_heartbeat(self):
        stats = self.broker.get_stats()
        pos = self.broker.open_position
        now_str = datetime.now().strftime('%H:%M:%S')
        if pos is not None:
            fl_pnl = pos.get('floating_pnl', 0.0)
            fl_r = pos.get('floating_r', 0.0)
            print(f"[{now_str}] [HEARTBEAT] ACTIVE: {pos['direction']} {pos['lot']:.2f}L | Floating PnL: {'+' if fl_pnl>=0 else ''}${fl_pnl:.2f} ({fl_r:+.2f}R) | Balance: ${self.broker.cash:.2f}")
        else:
            print(f"[{now_str}] [HEARTBEAT] STANDBY HUNTING | Balance: ${self.broker.cash:.2f} | Trades: {stats['total_trades']} (WR: {stats['win_rate']:.1f}%)")
        self._save_state()

    def _save_state(self):
        try:
            stats = self.broker.get_stats()
            state = {
                "session_id": "MOMENT_LOCKED_PROD",
                "model_choice": "pretrained",
                "model_name": "MOMENT-1-large Pretrained (Locked Production)",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "cash": self.broker.cash,
                "equity": self.broker.get_equity(),
                "initial_capital": self.broker.initial_capital,
                "lot_mode": self.broker.lot_mode,
                "max_lot": self.broker.max_lot,
                "open_position": self.broker.open_position,
                "broker": {
                    "cash": self.broker.cash,
                    "open_position": self.broker.open_position,
                    "stats": stats
                },
                "stats": stats,
                "recent_trades": self.broker.trade_history[-10:]
            }
            if self.db is not None:
                self.db.save_operational_state(state, "GLOBAL_STATE")

            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2, default=str)
        except Exception:
            pass

    def run(self):
        print_frame_banner()
        print("  Architecture: 15-Channel MOMENT LoRA + 4-Stage Kinetic OMS")
        print("  Mode        : Live Realtime Simulation (Zero Real Account Risk)")
        print(f"  Device      : {self.agent.device} (GPU PyTorch Runtime)")
        print(f"  Telegram    : {'Configured & Active' if self.telegram.is_active else 'Inactive (Optional: set TELEGRAM_BOT_TOKEN)'}")
        print(f"  State File  : {self.state_file}")
        print("==========================================================================")
        print("  Engine started in 24/7 background mode. Press Ctrl+C to terminate.")
        print("==========================================================================\n")

        self.feed.start()
        self.app.exec()

    def stop(self):
        print("\nStopping headless trader engine gracefully...")
        self.feed.stop()
        self.app.quit()

def main():
    trader = HeadlessLiveTrader(initial_capital=250.0, lot_mode="dynamic", max_lot=0.02)
    
    # Handle graceful exit
    signal.signal(signal.SIGINT, lambda sig, frame: trader.stop())
    signal.signal(signal.SIGTERM, lambda sig, frame: trader.stop())
    
    trader.run()

if __name__ == "__main__":
    main()
