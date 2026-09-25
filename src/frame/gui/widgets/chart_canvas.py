"""
Matplotlib Figure Canvas for FRAME Desktop Workstation
Clean, high-contrast dark aesthetic for equity curve & drawdown rendering.
Supports single-mode and dual-mode comparison (Flat 0.01 vs Dynamic Compounding).
"""

from typing import List, Dict, Any
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

try:
    from PySide6.QtWidgets import QWidget, QVBoxLayout
except ImportError:
    from PyQt6.QtWidgets import QWidget, QVBoxLayout

class ChartCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        plt.style.use('dark_background')
        self.fig, (self.ax_eq, self.ax_dd) = plt.subplots(
            2, 1, figsize=(10, 6), dpi=100, 
            gridspec_kw={'height_ratios': [2.2, 1.0], 'hspace': 0.28}
        )
        self.fig.patch.set_facecolor('#0d111a')

        self.canvas = FigureCanvas(self.fig)
        layout.addWidget(self.canvas)

        self._render_empty()

    def _render_empty(self):
        for ax in (self.ax_eq, self.ax_dd):
            ax.clear()
            ax.set_facecolor('#10141e')
            ax.grid(True, linestyle='--', alpha=0.12, color='#ffffff')
        self.ax_eq.set_title("EQUITY GROWTH CURVE — STANDING BY FOR AUDIT COMMANDS", fontsize=10, fontweight='bold', color='#8b949e', pad=8)
        self.ax_dd.set_title("UNDERWATER DRAWDOWN PROFILE (%)", fontsize=9, fontweight='bold', color='#8b949e', pad=6)
        self.canvas.draw()

    def plot_results(self, data: Dict[str, Any]):
        eq_curve = data.get('equity_curve', [])
        date_strs = data.get('equity_dates', [])
        initial_cap = data.get('initial_capital', 500.0)
        is_dual = data.get('dual_mode', False)

        if not eq_curve or len(eq_curve) < 2:
            return

        dates = pd.to_datetime(date_strs)

        # -------------------------------------------------------------
        # 1. Main Equity Plot
        # -------------------------------------------------------------
        self.ax_eq.clear()
        self.ax_eq.set_facecolor('#10141e')
        self.ax_eq.grid(True, linestyle='--', alpha=0.15, color='#ffffff')

        if is_dual and data.get('equity_curve_flat') and data.get('equity_curve_dyn'):
            curve_flat = data['equity_curve_flat']
            curve_dyn = data['equity_curve_dyn']
            final_flat = data.get('final_equity_flat', curve_flat[-1])
            ret_flat = data.get('ret_pct_flat', 0.0)
            dd_flat = data.get('max_dd_flat', 0.0)

            final_dyn = data.get('final_equity_dyn', curve_dyn[-1])
            ret_dyn = data.get('ret_pct_dyn', 0.0)
            dd_dyn = data.get('max_dd_dyn', 0.0)
            peak_lot = data.get('peak_lot', 0.01)

            # Flat curve (Cyan dashed)
            self.ax_eq.plot(
                dates, curve_flat, color='#00e5ff', linestyle='--', linewidth=1.6, alpha=0.9,
                label=f'Flat 0.01 Lot: ${final_flat:,.2f} ({ret_flat:+,.1f}%) | DD: {dd_flat:.1f}%'
            )
            # Dynamic Compounding curve (Green/Gold solid)
            self.ax_eq.plot(
                dates, curve_dyn, color='#00e676', linestyle='-', linewidth=2.0,
                label=f'Dynamic Compounding: ${final_dyn:,.2f} ({ret_dyn:+,.1f}%) | DD: {dd_dyn:.1f}% | Peak: {peak_lot:.2f}L'
            )
            self.ax_eq.fill_between(dates, initial_cap, curve_dyn, where=(np.array(curve_dyn) >= initial_cap), color='#00e676', alpha=0.08)

        else:
            final_eq = eq_curve[-1]
            c_curve = '#00e676' if final_eq >= initial_cap else '#ff5252'
            sizing_label = data.get('sizing_mode', 'flat').upper()
            self.ax_eq.plot(dates, eq_curve, color=c_curve, linewidth=1.8, label=f'{sizing_label}: ${final_eq:,.2f}')
            self.ax_eq.fill_between(dates, initial_cap, eq_curve, where=(np.array(eq_curve) >= initial_cap), color='#00e676', alpha=0.10)

        # Baseline horizontal line
        self.ax_eq.axhline(initial_cap, color='#ff1744', linestyle=':', linewidth=1.0, alpha=0.7, label=f'Initial: ${initial_cap:,.2f}')

        mode_title = data.get('mode', 'AUDIT')
        self.ax_eq.set_title(f"FLOWDEV FRAME — {mode_title} (CAPITAL: ${initial_cap:,.0f})", fontsize=11, fontweight='bold', color='#f0f6fc', pad=8)
        self.ax_eq.set_ylabel("Equity ($ USD)", fontsize=9, color='#8b949e')
        self.ax_eq.yaxis.set_major_formatter(ticker.StrMethodFormatter('${x:,.0f}'))
        self.ax_eq.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        self.ax_eq.legend(loc='upper left', framealpha=0.8, facecolor='#121824', edgecolor='#233148', fontsize=8.5)

        # -------------------------------------------------------------
        # 2. Drawdown Plot
        # -------------------------------------------------------------
        self.ax_dd.clear()
        self.ax_dd.set_facecolor('#10141e')
        self.ax_dd.grid(True, linestyle='--', alpha=0.15, color='#ffffff')

        if is_dual and data.get('equity_curve_flat') and data.get('equity_curve_dyn'):
            # Flat DD
            p_flat = np.maximum.accumulate(data['equity_curve_flat'])
            dd_f = (p_flat - data['equity_curve_flat']) / p_flat * 100
            self.ax_dd.plot(dates, -dd_f, color='#00e5ff', linestyle='--', linewidth=1.2, alpha=0.85, label=f'Flat Max DD: {data.get("max_dd_flat", 0):.1f}%')

            # Dyn DD
            p_dyn = np.maximum.accumulate(data['equity_curve_dyn'])
            dd_d = (p_dyn - data['equity_curve_dyn']) / p_dyn * 100
            self.ax_dd.fill_between(dates, 0, -dd_d, color='#ff1744', alpha=0.30)
            self.ax_dd.plot(dates, -dd_d, color='#ff5252', linewidth=1.2, label=f'Dyn Max DD: {data.get("max_dd_dyn", 0):.1f}%')

        else:
            peaks = np.maximum.accumulate(eq_curve)
            dds = (peaks - eq_curve) / peaks * 100
            max_dd = np.max(dds)
            self.ax_dd.fill_between(dates, 0, -dds, color='#ff1744', alpha=0.35)
            self.ax_dd.plot(dates, -dds, color='#ff5252', linewidth=1.0, label=f'Max DD: {max_dd:.2f}%')

        self.ax_dd.set_ylabel("Drawdown (%)", fontsize=8.5, color='#8b949e')
        self.ax_dd.yaxis.set_major_formatter(ticker.PercentFormatter())
        self.ax_dd.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        self.ax_dd.legend(loc='lower right', framealpha=0.8, facecolor='#121824', edgecolor='#233148', fontsize=8)

        self.fig.subplots_adjust(top=0.93, bottom=0.08, left=0.08, right=0.96, hspace=0.28)
        self.canvas.draw()
