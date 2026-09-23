"""
XAU_DEEP_SNIPER - Automatic Trailing Breakeven Manager (BAB 8.3)
================================================================
Aturan Eksekusi:
Ketika posisi berjalan mencapai floating profit >= +0.7R, Stop Loss secara
otomatis digeser ke harga entry ditambah biaya transaksi (Entry + Spread/Commission)
guna memastikan status bebas risiko (risk-free trade).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class BreakevenResult:
    is_breakeven_active: bool
    should_modify_sl: bool
    new_sl_price: float
    profit_locked_usd: float
    r_multiple_reached: float
    reason: str = ""


class TrailingBreakevenManager:
    """
    Manajer breakeven deterministik yang memperhitungkan biaya spread dan komisi.
    """

    def __init__(
        self,
        be_trigger_r: float = 0.7,        # Trigger pada +0.7R
        default_spread_pip: float = 0.75, # 0.75 pip = $0.075 price
        commission_per_lot: float = 3.50, # $3.50 per lot
        contract_size: float = 100.0,
    ):
        self.be_trigger_r = be_trigger_r
        self.default_spread_pip = default_spread_pip
        self.commission_per_lot = commission_per_lot
        self.contract_size = contract_size

    def calculate_friction_price(self, spread_pip: Optional[float] = None) -> float:
        """
        Menghitung total biaya gesekan (spread + komisi) dalam satuan harga emas.
        """
        s_pip = spread_pip if spread_pip is not None else self.default_spread_pip
        spread_price = s_pip * 0.10  # 1 pip emas = $0.10
        commission_price = self.commission_per_lot / self.contract_size  # $3.50 / 100 = $0.035
        return round(spread_price + commission_price, 3)

    def evaluate(
        self,
        action: str,                   # "BUY" atau "SELL"
        entry_price: float,
        initial_sl: float,
        current_sl: float,
        bar_high: float,
        bar_low: float,
        spread_pip: Optional[float] = None,
    ) -> BreakevenResult:
        """
        Evaluasi apakah posisi telah mencapai +0.7R dan perlu digeser ke breakeven.
        """
        action = action.upper()
        if action not in ["BUY", "SELL"]:
            raise ValueError(f"Invalid action: {action}")

        r_distance = abs(entry_price - initial_sl)
        if r_distance <= 0:
            return BreakevenResult(False, False, current_sl, 0.0, 0.0, "Invalid R distance")

        friction = self.calculate_friction_price(spread_pip)

        if action == "BUY":
            max_gain = bar_high - entry_price
            r_multiple = max_gain / r_distance
            target_be_sl = round(entry_price + friction, 2)

            if r_multiple >= self.be_trigger_r:
                # Hanya geser jika target SL lebih tinggi dari current SL
                if target_be_sl > current_sl:
                    return BreakevenResult(
                        is_breakeven_active=True,
                        should_modify_sl=True,
                        new_sl_price=target_be_sl,
                        profit_locked_usd=friction * self.contract_size,
                        r_multiple_reached=round(r_multiple, 3),
                        reason=f"BUY hit +{r_multiple:.2f}R >= +{self.be_trigger_r}R; moved SL to BE + friction ({target_be_sl})",
                    )
                else:
                    return BreakevenResult(
                        is_breakeven_active=True,
                        should_modify_sl=False,
                        new_sl_price=current_sl,
                        profit_locked_usd=friction * self.contract_size,
                        r_multiple_reached=round(r_multiple, 3),
                        reason="Breakeven already active",
                    )

        elif action == "SELL":
            max_gain = entry_price - bar_low
            r_multiple = max_gain / r_distance
            target_be_sl = round(entry_price - friction, 2)

            if r_multiple >= self.be_trigger_r:
                # Untuk SELL, SL baru harus lebih rendah dari current SL
                if target_be_sl < current_sl:
                    return BreakevenResult(
                        is_breakeven_active=True,
                        should_modify_sl=True,
                        new_sl_price=target_be_sl,
                        profit_locked_usd=friction * self.contract_size,
                        r_multiple_reached=round(r_multiple, 3),
                        reason=f"SELL hit +{r_multiple:.2f}R >= +{self.be_trigger_r}R; moved SL to BE - friction ({target_be_sl})",
                    )
                else:
                    return BreakevenResult(
                        is_breakeven_active=True,
                        should_modify_sl=False,
                        new_sl_price=current_sl,
                        profit_locked_usd=friction * self.contract_size,
                        r_multiple_reached=round(r_multiple, 3),
                        reason="Breakeven already active",
                    )

        return BreakevenResult(
            is_breakeven_active=False,
            should_modify_sl=False,
            new_sl_price=current_sl,
            profit_locked_usd=0.0,
            r_multiple_reached=round(r_multiple, 3),
            reason=f"Floating profit +{r_multiple:.2f}R below trigger +{self.be_trigger_r}R",
        )
