"""
XAU_DEEP_SNIPER - Concurrency & Confidence Threshold Gates (TAHAP 5)
=====================================================================
- ConcurrencyGate: Membatasi maksimal 1 posisi aktif simultan dan melarang hedging/konflik.
- ConfidenceThresholdGate: Memfilter sinyal probabilitas model hanya jika P(a) >= tau.
"""

from typing import List, Dict, Any, Tuple
import numpy as np


class ConcurrencyGate:
    """
    Gerbang pembatasan posisi aktif simultan untuk isolasi statistik murni.
    """

    def __init__(self, max_concurrent_positions: int = 1):
        self.max_concurrent_positions = max_concurrent_positions

    def can_open(
        self,
        current_positions: List[Dict[str, Any]],
        new_action: str,
    ) -> Tuple[bool, str]:
        """
        Validasi apakah pembukaan posisi baru diperbolehkan berdasarkan posisi yang sedang aktif.
        """
        new_action = new_action.upper()
        if new_action not in ["BUY", "SELL"]:
            return False, f"Invalid action: {new_action}"

        if len(current_positions) >= self.max_concurrent_positions:
            return False, f"Concurrency limit reached ({len(current_positions)}/{self.max_concurrent_positions} active trades)"

        # Cek konflik arah (dilarang membuka posisi berlawanan)
        for pos in current_positions:
            pos_action = pos.get("action", "").upper()
            if pos_action != new_action:
                return False, f"Hedging conflict: Cannot open {new_action} while {pos_action} position is active"

        return True, "Concurrency gate passed"


class ConfidenceThresholdGate:
    """
    Gerbang penyaring ambang keyakinan model (tau).
    """

    def __init__(self, default_tau: float = 0.35):
        if not (0.20 <= default_tau <= 0.90):
            raise ValueError(f"Confidence threshold tau must be in [0.20, 0.90], got {default_tau}")
        self.default_tau = default_tau

    def evaluate_signal(
        self,
        probabilities: np.ndarray,
        tau: float = None,
    ) -> Tuple[bool, int, float, str]:
        """
        Mengevaluasi apakah sinyal probabilitas non-HOLD melampaui batas ambang tau.
        Input: probabilities shape (5,) -> [P(HOLD), P(BUY_1R), P(BUY_2R), P(SELL_1R), P(SELL_2R)]
        Returns: (is_confident, best_action_class, confidence_score, reason)
        """
        threshold = tau if tau is not None else self.default_tau

        if len(probabilities) != 5:
            return False, 0, 0.0, "Probabilities must have 5 classes"

        # Kelas 1 s.d. 4 (Trade signals)
        trade_probs = probabilities[1:]
        max_idx = int(np.argmax(trade_probs))
        action_class = max_idx + 1
        confidence = float(trade_probs[max_idx])

        # Periksa apakah probabilitas non-HOLD melebihi tau
        if confidence >= threshold:
            # Periksa juga apakah keyakinan aksi mengalahkan HOLD (kelas 0)
            p_hold = float(probabilities[0])
            if confidence > p_hold:
                return True, action_class, confidence, f"Signal class {action_class} passed tau {threshold:.2f} (P={confidence:.3f} > P_hold={p_hold:.3f})"
            else:
                return False, 0, confidence, f"P_hold ({p_hold:.3f}) exceeds action prob ({confidence:.3f})"

        return False, 0, confidence, f"Confidence {confidence:.3f} below threshold {threshold:.2f}"
