"""
FLOWDEV FRAME - Real-Time Telegram Alert Notifier
Sends real-time trade execution, Kinetic OMS escalations, and performance updates
directly to your smartphone so you can monitor the bot 24/7 without opening your laptop.
"""

import os, json, urllib.request, urllib.parse
from typing import Optional, Dict, Any
from datetime import datetime, timezone

class LiveTelegramNotifier:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        self.is_active = bool(self.bot_token and self.chat_id)

    def send_message(self, text: str) -> bool:
        if not self.is_active:
            return False
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true"
            }).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "FlowdevFrame/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception as e:
            return False

    def notify_order_opened(self, pos: Dict[str, Any], balance: float):
        d_emoji = "🟢 BUY" if pos.get("direction") == "BUY" else "🔴 SELL"
        msg = (
            f"🦅 <b>FLOWDEV FRAME // NEW TRADE OPENED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Direction:</b> {d_emoji}\n"
            f"<b>Pair:</b> XAU/USD (Gold Spot M30)\n"
            f"<b>Lot Size:</b> <code>{pos.get('lot', 0.01):.2f} Lot</code>\n"
            f"<b>Entry Price:</b> <code>${pos.get('entry_price', 0.0):.2f}</code>\n"
            f"<b>Initial SL:</b> <code>${pos.get('current_sl', 0.0):.2f}</code> (Risk: ${pos.get('sl_dist', 0.0):.2f})\n"
            f"<b>Take Profit:</b> <code>${pos.get('current_tp', 0.0):.2f}</code> (+2.7R)\n"
            f"<b>Current Balance:</b> <code>${balance:,.2f} USD</code>\n"
            f"<b>Time:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
        )
        self.send_message(msg)

    def notify_oms_event(self, stage_name: str, details: str, new_sl: float):
        msg = (
            f"⚡ <b>KINETIC OMS ESCALATION</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Stage:</b> {stage_name}\n"
            f"<b>Event:</b> {details}\n"
            f"<b>New Locked SL:</b> <code>${new_sl:.2f}</code>\n"
            f"<b>Protection Status:</b> ACTIVE 🛡️"
        )
        self.send_message(msg)

    def notify_order_closed(self, trade: Dict[str, Any], stats: Dict[str, Any]):
        pnl = trade.get("net_pnl", 0.0)
        res_emoji = "💰 PROFIT" if pnl >= 0 else "🔻 LOSS"
        msg = (
            f"🏁 <b>TRADE CLOSED [{res_emoji}]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Direction:</b> {trade.get('direction')} ({trade.get('lot', 0.01):.2f} Lot)\n"
            f"<b>Exit Price:</b> <code>${trade.get('exit_price', 0.0):.2f}</code>\n"
            f"<b>Net PnL:</b> <code>{'+' if pnl>=0 else ''}${pnl:.2f} USD</code>\n"
            f"<b>Exit Reason:</b> {trade.get('exit_reason', 'Closed')}\n"
            f"<b>Bars Held:</b> {trade.get('bars_held', 1)} bars ({trade.get('bars_held', 1)*0.5:.1f} hrs)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>New Balance:</b> <code>${stats.get('cash', 0.0):,.2f} USD</code>\n"
            f"<b>Win Rate:</b> {stats.get('win_rate', 0.0):.1f}% ({stats.get('wins', 0)}W / {stats.get('losses', 0)}L)\n"
            f"<b>Total Return:</b> {stats.get('return_pct', 0.0):+.2f}%"
        )
        self.send_message(msg)
