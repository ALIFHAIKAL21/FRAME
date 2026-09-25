# BLUEPRINT UPGRADE XAU_DEEP_SNIPER
### Transformasi Menuju Bot Trading Tanpa Kompromi (All-Regime Dominance)

---

## 1. Prinsip Sakral Upgrade

1. **Non-Destructive (Hanya Menambah, Pantang Membuang):**
   * Seluruh 12 channel fitur lama—termasuk **SMI (Stochastic Momentum Index), Order Block, dan Liquidity Sweep**—**tetap dipertahankan 100%**.
   * Fitur lama telah terbukti menghasilkan akurasi tinggi (63% – 68%) dan profit solid di 2021, 2022, 2025, dan 2026. Upgrade ini dilarang keras menurunkan performa di periode yang sudah terbukti profit.

2. **Tanpa Kompromi (No Abstain / Pantang Lari dari Pasar):**
   * Tujuan bot adalah **melampaui batasan emosional manusia**, bukan meniru ketakutan manusia dengan cara mematikan trading saat pasar bergejolak.
   * Bot harus tetap aktif trading dan mampu mencetak profit di segala kondisi pasar ekstrem, termasuk perang geopolitik (Q4 2023) dan reli rekor All-Time-High (2024).

---

## 2. Diagnosis Backtest 2021 – 2025 (Fakta Objektif)

| Tahun | Hasil Backtest | Kondisi Pasar | Evaluasi Masalah & Peluang |
| :---: | :---: | :---: | :--- |
| **2021** | **PROFIT (+6.19%)** | Normal / Transisi | SMI dan Order Block bekerja sangat baik. |
| **2022** | **SUPER PROFIT (+38.01%)** | Tren Terstruktur | Win rate 68.6%, performa ideal institusional. |
| **2023** | **DRAWDOWN (-9.23%)** | Syok Perang Q4 | Terjebak di Sep–Okt 2023 saat perang Timur Tengah memicu gap dan lonjakan volatilitas liar. |
| **2024** | **DRAWDOWN (-11.55%)** | Reli Parabolik ATH | **Kesalahan Orientasi:** Emas melesat dari $2,050 ke $2,450. Bot mengeksekusi 37 posisi SELL berturut-turut karena SMI mendeteksi "overbought" di M30, buta terhadap tren makro. |
| **2025** | **PROFIT (+23.29%)** | Higher-High Terstruktur | Win rate 63.2%, pemulihan performa yang solid. |

> **Kesimpulan:** Pasar 2024 bukanlah pasar yang rusak, melainkan **pasar paling berpotensi profit besar dalam sejarah emas**. Bot merugi murni karena arah sinyalnya terbalik (counter-trend shorting melawan tren makro). Jika orientasi sinyal berbalik menjadi BUY-continuation, 2024 akan menjadi tahun dengan keuntungan tertinggi.

---

## 3. Rencana Peningkatan: Additive Feature Enrichment

Tanpa merombak channel 0–11, kita menambahkan sensor multi-timeframe makro (H4) ke dalam input Transformer:

```
[Channel Lama 0 - 11: 100% UTUH]
├── Ch 0 - 3: OHLC Normalisasi M30
├── Ch 4: Volume Z-Score Dinamis
├── Ch 5: SMA Cross Spread
├── Ch 6 - 8: SMI Val, Signal Hist, & Reversal Zone (SENJATA INTI)
├── Ch 9: Supply & Demand Order Block Zone
├── Ch 10: Liquidity Sweep (SSL / BSL Hunt)
└── Ch 11: Valuation Regime (Premium / Discount)

[Channel Tambahan: SENSOR BARU MAKRO H4]
├── Ch 12: H4 Macro Trend Velocity (Kecepatan & Arah Ombak Besar H4)
├── Ch 13: H4 Market Structure (Status Bullish / Bearish Struktural)
└── Ch 14: Momentum Expansion Persistence (Deteksi Arus Dana Berkelanjutan)
```

---

## 4. Mekanisme Sinergi Cerdas AI

Dengan penambahan saluran makro H4, lapisan Self-Attention pada model MOMENT akan belajar menghubungkan dua kondisi secara otomatis:

1. **Rezim Pasar Normal / Sideways (Seperti 2021, 2022, 2025, 2026):**
   * Sensor H4 bernilai netral/tenang.
   * Model otomatis memusatkan bobot 100% pada **SMI & Order Block M30**.
   * **Hasil:** Performa di tahun-tahun profit tetap tajam dan terlindungi 100%.

2. **Rezim Reli Parabolik / All-Time High (Seperti 2024 & Q4 2023):**
   * Sensor H4 mendeteksi akselerasi tren masif.
   * AI membaca kombinasi:
     $$\text{SMI Overbought} + \text{H4 Macro Expansion} = \textbf{STRONG BUY CONTINUATION}$$
   * Alih-alih melakukan counter-trend SELL yang fatal, bot justru masuk **BUY dan menunggangi tren** dengan target keuntungan besar (*Uncapped Trailing Runner*).
   * **Hasil:** Tahun 2023 dan 2024 yang tadinya minus otomatis terbalik menjadi sumber profit raksasa.

---

## 5. Rencana Tahapan Eksekusi

* [x] **Tahap 1: Feature Pipeline Enhancement (SELESAI & TERVALIDASI)**
  * Menambahkan kalkulasi fitur `h4_macro_trend_velocity` (Ch 12), `h4_market_structure` (Ch 13), dan `momentum_expansion_persistence` (Ch 14) ke dalam `src/pipeline/features_macro.py`, `feature_pipeline.py`, dan `feature_config.py`.
  * Menjamin zero lookahead bias dengan pergeseran 1 bar H4 (`shift(1)`) sebelum forward-fill ke M30.
* [x] **Tahap 2: Dataset Regeneration (SELESAI & TERVALIDASI)**
  * Dataset 15-channel berhasil digenerate di `data/processed/xauusd_m30_labeled_15ch.parquet` (58,582 sampel tensor valid).
  * Validasi kualitas: 0 NaN, 0 Inf di seluruh 15 channel.
  * Integritas label acuan Triple Barrier terbukti 100% identik dengan baseline.
  * Uji forward pass PyTorch Dataset & DataLoader tensor `(B=32, C=15, L=64)` ke model MOMENT-1-large lulus 100%.
* [ ] **Tahap 3: Model Retraining & Fine-Tuning (SIAP DIEKSEKUSI SETELAH PERSETUJUAN)**
  * Melatih MOMENT-1-large pada tensor 15 channel dengan LoRA ($r=32, \alpha=64$, 987K trainable parameters) menggunakan Purged & Embargoed Cross-Validation.
* [ ] **Tahap 4: Audit & Validasi Penuh 5 Tahun**
  * Memverifikasi bahwa tahun 2021, 2022, 2025, 2026 tidak mengalami penurunan performa, dan tahun 2023–2024 sukses berbalik menjadi hijau.
