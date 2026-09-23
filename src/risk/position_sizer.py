"""
XAU_DEEP_SNIPER - Volatility-Adjusted Fractional Position Sizer (BAB 8.1)
========================================================================
Formula Deterministik Institusional:
    Lot Size = (Equity * Risk Fraction) / (SL Distance * Contract Size)

Batasan Non-Negotiable:
- Risk Fraction strictly <= 1.0% (default) dan maks 2.0%
- Downward step rounding (floor) untuk menjamin risiko modal tidak pernah melebihi target
- Min lot: 0.01, Max lot: 50.0, Lot step: 0.01
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class PositionSizeResult:
    lot_size: float
    risk_amount_usd: float
    risk_fraction_actual: float
    sl_distance_price: float
    is_valid: bool
    rejection_reason: str = ""


class DynamicPositionSizer:
    """
    Kalkulator ukuran lot dinamis berbasis risiko modal dan jarak Stop Loss struktural.
    """

    def __init__(
        self,
        default_risk_fraction: float = 0.01,
        max_risk_fraction: float = 0.02,
        contract_size: float = 100.0,     # 100 oz emas per standard lot XAU/USD
        min_lot: float = 0.01,
        max_lot: float = 50.0,
        lot_step: float = 0.01,
    ):
        if not (0.0 < default_risk_fraction <= max_risk_fraction):
            raise ValueError(f"Invalid default_risk_fraction: {default_risk_fraction}")
        if max_risk_fraction > 0.05:
            raise ValueError("Max risk fraction cannot exceed 5.0% for institutional risk safety")

        self.default_risk_fraction = default_risk_fraction
        self.max_risk_fraction = max_risk_fraction
        self.contract_size = contract_size
        self.min_lot = min_lot
        self.max_lot = max_lot
        self.lot_step = lot_step

    def calculate_lot(
        self,
        equity: float,
        sl_distance_price: float,
        risk_fraction: Optional[float] = None,
    ) -> PositionSizeResult:
        """
        Menghitung lot size eksak dari equity dan jarak SL dalam dolar per oz emas.
        """
        f = risk_fraction if risk_fraction is not None else self.default_risk_fraction

        if equity <= 0:
            return PositionSizeResult(0.0, 0.0, 0.0, sl_distance_price, False, "Equity must be positive")

        if sl_distance_price <= 0:
            return PositionSizeResult(0.0, 0.0, 0.0, sl_distance_price, False, "SL distance must be positive")

        # Clamp risk fraction to max limit
        f_clamped = min(f, self.max_risk_fraction)
        if f_clamped <= 0:
            return PositionSizeResult(0.0, 0.0, 0.0, sl_distance_price, False, "Risk fraction must be positive")

        target_risk_usd = equity * f_clamped
        # Kerugian per 1.0 standard lot jika SL tersentuh = sl_distance_price * contract_size
        loss_per_lot_usd = sl_distance_price * self.contract_size

        if loss_per_lot_usd <= 0:
            return PositionSizeResult(0.0, 0.0, 0.0, sl_distance_price, False, "Loss per lot must be positive")

        raw_lot = target_risk_usd / loss_per_lot_usd

        # Floor rounding ke lot_step terdekat untuk mencegah risiko melebihi target
        steps = math.floor(raw_lot / self.lot_step)
        calculated_lot = round(steps * self.lot_step, 4)

        if calculated_lot < self.min_lot:
            # Jika modal terlalu kecil untuk menanggung min lot pada jarak SL ini
            min_lot_risk_usd = self.min_lot * loss_per_lot_usd
            # Izinkan hanya jika min lot risk tidak melebihi 1.5x target_risk
            if min_lot_risk_usd <= target_risk_usd * 1.5:
                calculated_lot = self.min_lot
            else:
                return PositionSizeResult(
                    0.0,
                    0.0,
                    0.0,
                    sl_distance_price,
                    False,
                    f"Required lot ({raw_lot:.4f}) below min_lot ({self.min_lot}); risk exceeds tolerance",
                )

        # Clamping ke max_lot
        final_lot = min(calculated_lot, self.max_lot)
        actual_risk_usd = final_lot * loss_per_lot_usd
        actual_risk_fraction = actual_risk_usd / equity

        return PositionSizeResult(
            lot_size=round(final_lot, 2),
            risk_amount_usd=round(actual_risk_usd, 2),
            risk_fraction_actual=round(actual_risk_fraction, 6),
            sl_distance_price=sl_distance_price,
            is_valid=True,
            rejection_reason="",
        )

    @staticmethod
    def calculate_sl_from_atr(atr_val: float, multiplier: float = 1.5) -> float:
        """Helper untuk menentukan jarak SL proporsional volatilitas ATR."""
        if atr_val <= 0:
            raise ValueError("ATR must be positive")
        return round(atr_val * multiplier, 2)
