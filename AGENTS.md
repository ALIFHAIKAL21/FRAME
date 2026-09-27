# CONSTITUTION & OPERATIONAL PROTOCOL: XAU_DEEP_SNIPER
# Dedicated Quantitative Deep Learning System for XAU/USD (Gold) M30
# fokus pada folder proyek xau_deep_sniper (tidak yang lain)

## 1. Core Mission & Identity
Repository ini adalah lingkungan riset kuantitatif murni (pure quantitative research environment) tingkat institusional untuk membangun model Deep Learning / Foundation Time-Series Model (MOMENT-1-large) khusus instrumen XAU/USD pada timeframe 30-Menit (M30).

Tujuan tunggal: Menghasilkan model probabilitas arah dan trajektori harga yang memiliki keunggulan statistik (positive expected value / statistical edge) net-of-cost, dengan batasan risiko deterministik yang ketat.

---

## 2. Hard Boundaries & Prohibitions (Pantangan Mutlak)
Semua AI Agent (Antigravity dan sub-agent) yang beroperasi di repositori ini WAJIB mematuhi pantangan berikut:
1. **DILARANG Toy Bot / Grid / Martingale**: Tidak ada algoritma averaging down, grid trading, atau martingale. Setiap transaksi memiliki structural stop-loss wajib.
2. **DILARANG Generic LLM Wrapper**: Tidak ada pemanggilan API OpenAI/Claude/Gemini untuk membaca chart atau memberikan sinyal eksekusi trading.
3. **DILARANG Membangun UI / Dashboard / Web App**: Seluruh fase riset, data engineering, feature generation, labeling, dan training dilakukan tanpa GUI/web frontend. Fokus 100% pada data pipeline, validasi, dan model.
4. **DILARANG Menyuapkan Raw Price ke Model**: Harga nominal Gold ($1,500 - $2,700+) tidak boleh dimasukkan mentah ke model. Semua fitur harga WAJIB diubah menjadi scale-free stationary features (dinormalisasi terhadap local rolling EMA dan ATR).
5. **DILARANG Mengabaikan Slippage & Komisi**: Seluruh simulasi label, evaluasi, dan backtesting wajib memperhitungkan spread dinamis (min 2.5 - 3.5 pips) + komisi ($7/lot round-turn) + slippage (0.5 - 1.0 pip).
6. **DILARANG Melompati Tahapan**: Eksekusi harus bertahap sesuai 10 Bab di `RESEARCH_SPECIFICATION.md`. Step 4 (setup virtual environment & dependencies berat) ditahan sampai dataset dan pipeline siap.

---

## 3. Spesifikasi Arsitektur Sistem
Sistem ini menggunakan arsitektur **Single Deep Learning Model + Dual Deterministic Hard Gates**:

### A. Model Inti: Time-Series Foundation Model
- **Base Architecture**: `AutonLab/MOMENT-1-large` (385M parameter transformer foundation model) fine-tuned via LoRA (Low-Rank Adaptation) dengan rank $r=16$.
- **Objective**: 3-Class Classification (`BUY`, `SELL`, `HOLD/NEUTRAL`).
- **Loss Function**: Class-Balanced Focal Loss ($\gamma = 2.0$) untuk mengatasi dominasi kelas sideways/chop.

### B. Gate 1: Hard News Blackout Gate (Deterministik)
- Freeze total trading pada $T \pm 30$ menit di sekitar rilis berita High-Impact USD/XAU (NFP, CPI, FOMC, PPI, Retail Sales).
- Tidak ada inferensi model, tidak ada prediksi teks sentimen berita historis yang rentan revision bias.

### C. Gate 2: Hard Risk Management Gate (Deterministik)
- **Position Sizing**: Formula matematis dinamis berdasarkan persentase modal ($1\% - 2\%$) dibagi jarak Structural Invalidation Stop Loss.
- **Risk-Reward (RR)**: Target TP di 1:1 dan 1:2.
- **Trailing Breakeven**: Pindahkan SL ke BEP (Entry + buffer spread) saat profit mencapai $+0.7R$.
- **Friday Close-Out**: Likuidasi seluruh posisi terbuka setiap Jumat pukul 20:00 UTC untuk mengeliminasi weekend gap risk.
- **Weekly Circuit Breaker**: Jika drawdown mingguan menyentuh 5%, trading berhenti total hingga rollover minggu berikutnya. Batas absolut structural fail-safe modal adalah 50%.

---

## 4. Standar Dataset & Trajectory Labeling
1. **Dataset Depth**: 3 hingga 5 tahun data M30 OHLCV bersih dalam zona waktu UTC standar.
2. **Quality Checks**:
   - DST (Daylight Saving Time) shift harmonization.
   - Deteksi flat bar / missing candles / weekend filtering.
   - Rollover quarantine pada pukul 21:00 - 22:00 UTC (spread abnormal).
3. **Triple Barrier Trajectory Generation**:
   - Menghasilkan trajektori data dari ribuan baris bar dengan kombinasi titik entry potensial, upper barrier (TP 1:1 dan 1:2), lower barrier (structural SL), dan vertical barrier (maksimal bar penahanan).
   - Label dihitung net-of-cost secara realistis.

---

## 5. Validasi & Pengujian Ilmiah (Non-Negotiable)
Model dilarang dioperasikan sebelum melewati 3 Hard Scientific Gates:
- **Gate 1 (Out-of-Sample Performance)**:
  - Purged Walk-Forward Cross Validation (PWF-CV) dengan Embargo period untuk mencegah leakage time-series.
  - Out-of-sample Profit Factor $\ge 1.35$ dan Sharpe Ratio annualized $\ge 1.4$.
- **Gate 2 (Monte Carlo Stress Test)**:
  - 1,000 iterasi permutasi trade shuffle.
  - 95th percentile Worst-case Drawdown $\le 18\%$.
- **Gate 3 (Latency & Execution Simulation)**:
  - Simulasi adverse slippage eksekusi dan variasi spread.

---

## 6. Protokol Komunikasi & Kerja Agent
- Gunakan bahasa yang realistis, kritis, berbasis data, tajam, dan bebas optimisme semu.
- Utamakan pembuktian matematis dan statistik sebelum mengambil keputusan arsitektur.
- Setiap perubahan kode harus terdokumentasi, reproducible, dan modular di direktori `src/`.
