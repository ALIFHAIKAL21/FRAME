# CHECKPOINT PRODUCTION LOCK: XAU DEEP SNIPER
**Status: FROZEN / PRODUCTION READY (CHECKPOINT TERAKHIR)**  
**Tanggal Kunci:** 25 September 2026  
**Pair:** XAU/USD (Gold Spot vs US Dollar)  
**Timeframe Operasional:** M30 (30-Minute Bars)  
**Primary Execution Engine:** `scripts/run_500_smart_optimized_production.py`  
**Model Architecture:** 15-Channel Institutional Temporal Deep Network (Residual Moment Transformer / CNN-LSTM)

---

## 1. Aturan Kunci Modal & Manajemen Risiko (FROZEN)

| Parameter | Nilai Kunci | Keterangan & Rasional |
|---|---|---|
| **Modal Awal (Anchor)** | **$500.00 USD** | Kunci modal akun riil dasar. |
| **Ukuran Lot (Lot Size)** | **0.01 Lot Flat** | **MUTLAK: Tanpa eskalasi, tanpa compounding/martingale.** |
| **Contract Size** | 100 oz per lot | 0.01 lot = 1 oz emas ($1 per $1.00 pergerakan harga emas). |
| **Margin Minimum Level** | > 1,200% | Beban margin hanya ~$25–$28. Sangat aman dari Margin Call. |
| **Friksi Broker Total** | **$0.17 per trade** | Spread 0.75 pip ($0.075) + Slippage 0.3 pip 2-way ($0.03) + Komisi $3.50/lot ($0.035). |

---

## 2. Struktur Sesi & Frekuensi Trade Harian (4–5 Trades/Hari)

Trade dieksekusi secara ketat hanya pada 5 jendela likuiditas institusional (maksimal 1 trade per sesi):

1. **Sesi 1: Asia Early** (01:00 – 04:00 UTC / 08:00 – 11:00 WIB)
2. **Sesi 2: Asia Late** (04:30 – 07:00 UTC / 11:30 – 14:00 WIB)
3. **Sesi 3: London Core** (08:30 – 12:30 UTC / 15:30 – 19:30 WIB)
4. **Sesi 4: NY Open** (13:00 – 17:00 UTC / 20:00 – 00:00 WIB)
5. **Sesi 5: NY Core** (17:30 – 21:00 UTC / 00:30 – 04:00 WIB)

* **Filter Blackout Gap:** Bar jam 07:00 – 08:30 UTC diblokir dari entri baru (zona transisi pra-London).
* **Filter Akhir Pekan (Weekend Shield):** Jumat setelah pukul 18:00 UTC dilarang membuka posisi baru. Seluruh posisi aktif ditutup paksa (*auto-closeout*) pada Jumat pukul 20:00 UTC guna menghindari gap harga Senin.

---

## 3. Parameter Model & Sinyal Gating (FROZEN)

* **Confidence Threshold ($\tau_{\text{base}}$):** `0.32`
* **Uncertainty Margin Filter:** `Margin = p_best - p_hold >= 0.01`
* **Sequence Offset:** 63 bar (M30 lookback window)

---

## 4. Mekanisme Trade Management & Smart Protection (FROZEN)

Sistem menggunakan arsitektur proteksi 4 tahap yang telah diuji dan divalidasi:

1. **Stop Loss Awal:**  
   $$\text{SL Distance} = 1.5 \times \text{ATR}(14) \quad (\approx \$8.00 - \$15.00)$$
2. **Tahap 1: Positif Breakeven (+1.0R):**  
   Saat harga menyentuh $+1.0R$, SL otomatis digeser ke $\text{Entry} + \$0.25$ buffer. Menggaransi keuntungan bersih $+\$0.08$ jika tersenggol kembali.
3. **Tahap 2: Tiered Smart Ratchet (+1.2R):**  
   Saat harga mencapai $+1.2R$, SL otomatis dikunci ke $+0.5R$. Mengamankan profit pasti $+\$5.50 - \$9.00$ per trade dan mengeliminasi fenomena *open gain evaporation* di pasar konsolidasi.
4. **Tahap 3: Dynamic Trailing Stop (+1.5R+):**  
   Saat harga menembus $+1.5R$, Trailing Stop dinamis diaktifkan dengan jarak ketat $0.6R$ di belakang titik tertinggi harga.
5. **Tahap 4: Stale Decay Time Protection (Bar 10):**  
   Jika posisi telah tertahan selama 10 bar (5 jam) dan belum mampu memicu Breakeven, SL otomatis diperketat dari $-1.0R$ menjadi $-0.6R$ (memotong risiko loss hingga 40%).
6. **Kinetic Target Expansion (Max TP):**  
   Target Take Profit maksimum dipatok pada $+2.7R$ untuk memanen ekspansi momentum gelombang besar.
7. **Time Barrier Hard Exit:**  
   Maksimal durasi penahanan posisi adalah 12 bar (6 jam).

---

## 5. Audit Kinerja Resmi Terkunci (Januari – Agustus 2026)

*Data di bawah ini adalah tolok ukur resmi (*benchmark baseline*) yang diverifikasi secara matematis:*

| Metrik Kinerja | Nilai Audit Resmi | Catatan Validasi |
|---|---|---|
| **Modal Awal** | **$500.00 USD** | Modal riil akun |
| **Saldo Akhir Akun** | **$3,853.82 USD** | Bertumbuh +$3,353.82 |
| **Persentase Keuntungan Bersih** | **+670.76%** | Bersih setelah semua friksi |
| **Total Trade Dieksekusi** | **706 Trade** | Rata-rata 4.13 trade/hari |
| **Menang / Kalah** | **418 Menang / 288 Kalah** | **Menang > Kalah Mutlak** |
| **Overall Win Rate** | **59.21%** | Konsisten di atas 50% |
| **Profit Factor** | **1.52** | Rasio keuntungan terhadap kerugian |
| **Max Drawdown Portofolio** | **51.21%** | Floating drawdown dari puncak |
| **Titik Saldo Terendah (Dip)** | **$348.65 USD** | Terjadi di pertengahan Januari |
| **Konsistensi Frekuensi Harian** | **78.1% Hari (4–5 Trade)** | Stabilitas ritme terjaga |

### Tabel Performa Bulan ke Bulan (100% HIJAU)

| Bulan | Total Trade | Menang / Kalah | Win Rate (%) | Net PnL ($) | Saldo Akun Akhir Bulan |
|---|---|---|---|---|---|
| **Januari 2026** | 84 | 43 / 41 | **51.2%** | **+$104.53** | $604.53 |
| **Februari 2026** | 90 | 60 / 30 | **66.7%** | **+$878.64** | $1,483.17 |
| **Maret 2026** | 91 | 59 / 32 | **64.8%** | **+$666.87** | $2,150.04 |
| **April 2026** | 88 | 50 / 38 | **56.8%** | **+$293.45** | $2,443.49 |
| **Mei 2026** | 81 | 44 / 37 | **54.3%** | **+$121.70** | $2,565.19 |
| **Juni 2026** | 84 | 47 / 37 | **56.0%** | **+$352.92** | $2,918.11 |
| **Juli 2026** | 96 | 61 / 35 | **63.5%** | **+$605.36** | $3,523.47 |
| **Agustus 2026** | 92 | 54 / 38 | **58.7%** | **+$330.35** | **$3,853.82** |

---

## 6. Arsip File Terkait (Repository Assets)

1. **Script Eksekusi Produksi:**  
   [`scripts/run_500_smart_optimized_production.py`](file:///c:/Ngoding/bot_trading/scripts/run_500_smart_optimized_production.py)
2. **Laporan JSON Audit Lengkap:**  
   [`reports/backtest_500_modal_smart_optimized.json`](file:///c:/Ngoding/xau_deep_sniper/reports/backtest_500_modal_smart_optimized.json)
3. **Chart Tearsheet PNG (Resolusi Tinggi):**  
   [`reports/img/backtest_500_modal_smart_optimized.png`](file:///c:/Ngoding/xau_deep_sniper/reports/img/backtest_500_modal_smart_optimized.png)
4. **Dataset Fitur 15-Channel:**  
   `data/processed/xauusd_m30_labeled_15ch.parquet`
5. **Tensor Prediksi Model 15-Channel:**  
   `checkpoints/predictions_15ch.npy`

---

> **PROTOKOL KUNCI PERMANEN:**  
> Dilarang mengubah konstanta parameter di atas (`INITIAL_EQUITY = 500`, `FIXED_LOT = 0.01`, `RATCHET_12_R = 0.5`, `TRAIL_DIST_R = 0.6`, `TP_MAX_R = 2.7`, `STALE_DECAY_BARS = 10`) tanpa pengujian komparatif formal out-of-sample baru. Dokumen ini menjadi acuan mutlak (*single source of truth*) untuk implementasi live execution dan paper trading.

---

## 7. Aturan Default Perintah "Backtest" (User Contract)

**Mulai 25 September 2026:**  
Setiap kali pengguna/USER memberikan instruksi atau kata **"backtest"** tanpa spesifikasi parameter baru:
1. Sistem **100% WAJIB** menggunakan konfigurasi yang tercantum dalam dokumen ini tanpa ada modifikasi sedikit pun.
2. Engine yang dijalankan adalah: [`scripts/run_500_smart_optimized_production.py`](file:///c:/Ngoding/bot_trading/scripts/run_500_smart_optimized_production.py).
3. Parameter modal otomatis terkunci di **$500.00**, lot **0.01 flat**, dan seluruh filter 4 tahap proteksi aktif 100%.
