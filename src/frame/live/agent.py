"""
FLOWDEV FRAME - Live Strategy Agent & Kinetic 4-Stage OMS Controller
Combines the 15-channel MOMENT Neural Network with the locked 4-Stage Kinetic OMS:
Stage 1: Micro-Breakeven (+0.75R Acceleration)
Stage 2: Smart Ratchet (+1.2R / Lock 0.5R)
Stage 3: Dynamic Trailing Stop (+1.5R+)
Stage 4: Stale Decay (Bar 6 / -0.45R)
Ceiling: Max TP (+2.7R) & Time Barrier (12 Bars / 6h)
"""

import time, math, pathlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import numpy as np
import pandas as pd
import torch

try:
    from PySide6.QtCore import QObject, Signal
except ImportError:
    try:
        from PyQt6.QtCore import QObject, pyqtSignal as Signal
    except ImportError:
        class QObject:
            def __init__(self, parent=None): pass
        class Signal:
            def __init__(self, *args, **kwargs):
                self._cbs = []
            def connect(self, cb):
                if cb not in self._cbs:
                    self._cbs.append(cb)
            def emit(self, *args, **kwargs):
                for cb in list(self._cbs):
                    try: cb(*args, **kwargs)
                    except Exception: pass

from src.frame.constants import (
    SL_ATR_MULT, TP_MAX_R, BE_TRIGGER_R, BE_BUFFER_PRICE, RATCHET_12_R,
    TRAIL_TRIGGER_R, TRAIL_DIST_R, STALE_DECAY_BARS, STALE_DECAY_R, TIME_BARRIER_BARS,
    TAU_BASE, UNCERTAINTY_MARGIN, SESSION_WINDOWS_UTC, BLACKOUT_PRE_LONDON_START_UTC,
    BLACKOUT_PRE_LONDON_END_UTC, WEEKEND_SHIELD_NO_ENTRY_HOUR_UTC, WEEKEND_SHIELD_FORCE_CLOSE_HOUR_UTC
)
from .paper_broker import LivePaperBroker

class LiveAgent(QObject):
    order_opened = Signal(dict)
    order_closed = Signal(dict)
    position_updated = Signal(dict)
    oms_event = Signal(str, str, float)
    telemetry_updated = Signal(dict)
    agent_status_changed = Signal(bool, str)

    def __init__(self, broker: LivePaperBroker, parent=None):
        super().__init__(parent)
        self.broker = broker
        self.is_armed = True
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.last_evaluated_bar_time = 0
        self.last_session_traded = ""
        
        # Load MOMENT PyTorch model
        self._load_model()

    def _load_model(self):
        try:
            ckpt_path = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\checkpoints\best_moment_15ch_lora.pt")
            model_code_path = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\src\models\moment_model.py")
            if ckpt_path.exists() and model_code_path.exists():
                import importlib.util, sys
                spec = importlib.util.spec_from_file_location("src.models.moment_model", model_code_path)
                mod = importlib.util.module_from_spec(spec)
                sys.modules["src.models.moment_model"] = mod
                spec.loader.exec_module(mod)

                ckpt = torch.load(ckpt_path, map_location=self.device, weights_only=False)
                model_cfg = ckpt.get("config", None) or mod.MOMENTConfig(
                    n_channels=15, seq_len=64, patch_len=8, patch_stride=8,
                    d_model=1024, num_layers=6, num_heads=16, d_ff=2816,
                    dropout=0.2, num_classes=5, use_lora=True, lora_r=32, lora_alpha=64
                )
                self.model = mod.MOMENTClassifier(model_cfg).to(self.device)
                self.model.load_state_dict(ckpt["model_state_dict"])
                self.model.eval()
        except Exception as e:
            self.model = None

    def set_armed(self, armed: bool):
        self.is_armed = armed
        status_text = "ARMED // ACTIVELY SCANNING" if armed else "DISARMED // STANDBY"
        self.agent_status_changed.emit(armed, status_text)

    def get_current_session(self, dt_utc: datetime) -> Optional[str]:
        h = dt_utc.hour + (dt_utc.minute / 60.0)
        dow = dt_utc.weekday()

        # Weekend blackout
        if dow == 4 and h >= WEEKEND_SHIELD_NO_ENTRY_HOUR_UTC:
            return None
        if dow in [5, 6]:
            return None

        # Pre-London blackout
        if BLACKOUT_PRE_LONDON_START_UTC <= h < BLACKOUT_PRE_LONDON_END_UTC:
            return None

        for s_name, w_st, w_en in SESSION_WINDOWS_UTC:
            if w_st <= h <= w_en:
                return s_name
        return None

    def on_tick(self, tick_data: dict):
        if not self.is_armed:
            return

        bid = tick_data["bid"]
        ask = tick_data["ask"]
        pos = self.broker.open_position

        if pos is not None:
            # 1. Update floating PnL and check SL/TP hit
            closed_trade = self.broker.update_tick(bid, ask)
            if closed_trade is not None:
                self.order_closed.emit(closed_trade)
                return

            # 2. Real-time Kinetic 4-Stage OMS Progression
            self._evaluate_kinetic_oms(bid, ask)

            # 3. Emit position update
            self.position_updated.emit(self.broker.open_position)

    def _evaluate_kinetic_oms(self, bid: float, ask: float):
        pos = self.broker.open_position
        if pos is None:
            return

        d = pos["direction"]
        ep = pos["entry_price"]
        sl_dist = pos["sl_dist"]
        cur_price = bid if d == "BUY" else ask
        r_gain = (cur_price - ep) / sl_dist if d == "BUY" else (ep - cur_price) / sl_dist

        # Stage 1: Positive Micro-Breakeven (+0.75R)
        if not pos["be_activated"] and r_gain >= BE_TRIGGER_R:
            pos["be_activated"] = True
            new_sl = round(ep + BE_BUFFER_PRICE, 2) if d == "BUY" else round(ep - BE_BUFFER_PRICE, 2)
            pos["current_sl"] = max(pos["current_sl"], new_sl) if d == "BUY" else min(pos["current_sl"], new_sl)
            self.oms_event.emit("Stage 1: Micro-Breakeven", f"+{r_gain:.2f}R hit -> SL to Entry + ${BE_BUFFER_PRICE:.2f}", pos["current_sl"])

        # Stage 2: Smart Ratchet (+1.2R -> Lock +0.5R)
        if not pos["ratchet_activated"] and r_gain >= 1.2:
            pos["ratchet_activated"] = True
            new_sl = round(ep + (RATCHET_12_R * sl_dist), 2) if d == "BUY" else round(ep - (RATCHET_12_R * sl_dist), 2)
            pos["current_sl"] = max(pos["current_sl"], new_sl) if d == "BUY" else min(pos["current_sl"], new_sl)
            self.oms_event.emit("Stage 2: Smart Ratchet", f"+{r_gain:.2f}R hit -> Locked +0.5R Net Profit", pos["current_sl"])

        # Stage 3: Dynamic Trailing Stop (+1.5R+)
        if r_gain >= TRAIL_TRIGGER_R:
            peak = pos["peak_price"]
            new_sl = round(peak - (TRAIL_DIST_R * sl_dist), 2) if d == "BUY" else round(peak + (TRAIL_DIST_R * sl_dist), 2)
            if (d == "BUY" and new_sl > pos["current_sl"]) or (d == "SELL" and new_sl < pos["current_sl"]):
                pos["current_sl"] = new_sl
                pos["trail_activated"] = True
                self.oms_event.emit("Stage 3: Trailing Stop", f"Peak ${peak:.2f} -> Trailing SL updated", pos["current_sl"])

        # Stage 4: Stale Decay at Bar 6 (-0.45R)
        if pos["bars_held"] >= STALE_DECAY_BARS and not pos["be_activated"] and not pos["stale_decay_activated"]:
            pos["stale_decay_activated"] = True
            new_sl = round(ep - (STALE_DECAY_R * sl_dist), 2) if d == "BUY" else round(ep + (STALE_DECAY_R * sl_dist), 2)
            pos["current_sl"] = new_sl
            self.oms_event.emit("Stage 4: Stale Decay", f"Bar {pos['bars_held']} stale -> Cut SL to -0.45R (55% risk reduction)", pos["current_sl"])

        # Hard Time Barrier (12 bars / 6h)
        if pos["bars_held"] >= TIME_BARRIER_BARS:
            trade = self.broker.close_order(cur_price, exit_reason="Time Barrier (6h)")
            self.order_closed.emit(trade)
            self.oms_event.emit("Time Barrier", "Max 12 bars (6 hours) reached. Closed position.", cur_price)

    def on_candle_closed(self, candle: dict, recent_candles: List[dict]):
        if not self.is_armed:
            return

        c_time = candle["time"]
        if c_time == self.last_evaluated_bar_time:
            return
        self.last_evaluated_bar_time = c_time

        # Update bars_held for active position
        pos = self.broker.open_position
        if pos is not None:
            pos["bars_held"] += 1
            self.position_updated.emit(pos)

        # If already in trade, do not scan for new entry (1 concurrent trade allowed)
        if self.broker.open_position is not None:
            return

        # Check session eligibility
        dt_utc = datetime.fromtimestamp(c_time, timezone.utc)
        cur_session = self.get_current_session(dt_utc)
        if cur_session is None or cur_session == self.last_session_traded:
            return

        # Compute ATR(14) from recent candles
        if len(recent_candles) < 20:
            return

        highs = [c["high"] for c in recent_candles[-15:]]
        lows = [c["low"] for c in recent_candles[-15:]]
        closes = [c["close"] for c in recent_candles[-16:-1]]
        trs = []
        for i in range(len(highs)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i]), abs(lows[i] - closes[i]))
            trs.append(tr)
        atr_val = float(np.mean(trs)) if trs else 4.5
        sl_dist = round(max(3.0, atr_val * SL_ATR_MULT), 2)

        # Run AI Inference
        action, conf, probs = self._infer_signal(recent_candles)
        
        telemetry = {
            "time": dt_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "session": cur_session,
            "atr": round(atr_val, 2),
            "sl_dist": sl_dist,
            "action": action,
            "conf": round(conf * 100, 1),
            "probs": [round(float(p) * 100, 1) for p in probs] if probs is not None else []
        }
        self.telemetry_updated.emit(telemetry)

        # Gating Check
        p_hold = probs[0] if probs is not None else 0.5
        margin = conf - p_hold

        if action in ["BUY", "SELL"] and conf >= TAU_BASE and margin >= UNCERTAINTY_MARGIN:
            last_c = recent_candles[-1]
            bid = last_c["close"]
            ask = round(bid + 0.35, 2)
            new_pos = self.broker.open_order(
                direction=action,
                current_bid=bid,
                current_ask=ask,
                sl_dist=sl_dist,
                timestamp=dt_utc,
                reason=f"MOMENT {action} ({conf*100:.1f}%)"
            )
            self.last_session_traded = cur_session
            self.order_opened.emit(new_pos)

    def _infer_signal(self, candles: List[dict]):
        """
        Runs MOMENT PyTorch inference on the last 64 bars.
        If GPU/Model is offline, uses high-correlation momentum indicator consensus.
        """
        if self.model is not None and len(candles) >= 64:
            try:
                # Fast feature extraction
                df_c = pd.DataFrame(candles[-64:])
                # Synthetic or extracted 15 channels
                c = df_c['close'].values
                h = df_c['high'].values
                l = df_c['low'].values
                o = df_c['open'].values
                v = df_c['volume'].values

                ma9 = pd.Series(c).rolling(9, min_periods=1).mean().values
                ma21 = pd.Series(c).rolling(21, min_periods=1).mean().values
                spread_ma = (ma9 - ma21) / (np.std(c) + 1e-6)

                # Normalized 15-channel array
                feat_matrix = np.zeros((15, 64), dtype=np.float32)
                norm_base = ma21
                feat_matrix[0] = (o - norm_base) / 10.0
                feat_matrix[1] = (h - norm_base) / 10.0
                feat_matrix[2] = (l - norm_base) / 10.0
                feat_matrix[3] = (c - norm_base) / 10.0
                feat_matrix[4] = (v - np.mean(v)) / (np.std(v) + 1e-6)
                feat_matrix[5] = spread_ma
                feat_matrix[6] = np.clip(spread_ma * 0.8, -1.0, 1.0)
                feat_matrix[7] = np.gradient(spread_ma)
                feat_matrix[8] = np.where(spread_ma > 0.5, 1.0, np.where(spread_ma < -0.5, -1.0, 0.0))
                feat_matrix[9] = np.where(c > ma9, 1.0, -1.0)
                feat_matrix[10] = np.where(h > np.roll(h, 1), 1.0, -1.0)
                feat_matrix[11] = (c - np.min(l)) / (np.max(h) - np.min(l) + 1e-6) * 2.0 - 1.0
                feat_matrix[12] = np.clip((c[-1] - c[0]) / 20.0, -1.0, 1.0)
                feat_matrix[13] = 1.0 if c[-1] > ma21[-1] else -1.0
                feat_matrix[14] = np.clip(np.mean(feat_matrix[0:4], axis=0), -1.0, 1.0)

                x = torch.from_numpy(feat_matrix).unsqueeze(0).to(self.device)
                with torch.no_grad():
                    logits = self.model(x)
                    probs = torch.softmax(logits, dim=-1).cpu().numpy()[0]

                t_probs = probs[1:]
                max_i = int(np.argmax(t_probs))
                conf = float(t_probs[max_i])
                act = "BUY" if max_i in [0, 1] else "SELL"
                return act, conf, probs
            except Exception:
                pass

        # Indicator Consensus Fallback
        c = [bar["close"] for bar in candles]
        if len(c) >= 20:
            ema9 = float(pd.Series(c).ewm(span=9).mean().iloc[-1])
            ema21 = float(pd.Series(c).ewm(span=21).mean().iloc[-1])
            diff = (ema9 - ema21) / ema21
            if diff > 0.0008:
                return "BUY", 0.48, [0.20, 0.48, 0.16, 0.08, 0.08]
            elif diff < -0.0008:
                return "SELL", 0.48, [0.20, 0.08, 0.08, 0.48, 0.16]

        return "HOLD", 0.20, [0.60, 0.10, 0.10, 0.10, 0.10]

    def manual_close(self, current_price: float):
        if self.broker.open_position is not None:
            trade = self.broker.close_order(current_price, exit_reason="Manual Panic Close")
            self.order_closed.emit(trade)
            self.oms_event.emit("Manual Panic Close", "User closed order immediately.", current_price)
