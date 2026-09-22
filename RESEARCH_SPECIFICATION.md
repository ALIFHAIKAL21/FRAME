# SPESIFIKASI TEKNIS RISET DAN FONDASI DATA SCIENCE (CETAK BIRU LENGKAP)
## Aset: XAU/USD | Timeframe: 30 Menit (M30) | Paradigma: End-to-End Time-Series Foundation Model

---

### BAB 1: DEFINISI MASALAH DAN RUANG LINGKUP

1.1. Tujuan Riset
Membangun satu agen pengambil keputusan trading berbasis Time-Series Foundation Model yang beroperasi secara selektif pada instrumen XAU/USD timeframe 30 menit (M30). Model dilatih murni untuk mengenali struktur momentum terverifikasi, likuiditas pasar, serta Supply & Demand dengan target Risk:Reward (RR) terukur 1:1 dan 1:2.

1.2. Parameter Batasan Riset
- Pasangan Tunggal: XAU/USD (Gold).
- Timeframe Tunggal: 30 Menit (48 bar per hari perdagangan 24 jam).
- Cakupan Data: 5 tahun data historis M30 (sekitar 60.000 baris candle).
- Filosofi Operasional: Eksekusi selektif (Sniper). Tindakan default adalah HOLD (90% waktu berada di luar pasar).
- Batas Risiko Finansial: Risiko per transaksi dikunci pada 1% hingga 2% modal; batas toleransi drawdown mingguan diproteksi ketat oleh circuit breaker deterministik.

---

### BAB 2: AKUISISI DATA, PEMBERSIHAN, DAN ANOMALI MIKROSTRUKTUR

2.1. Sinkronisasi Waktu dan Pergeseran Daylight Saving Time (DST)
- Seluruh stempel waktu distandarisasi ke UTC absolut.
- Algoritma pembersih data wajib menerapkan kalender DST historis US dan UK untuk menyesuaikan jam pembukaan sesi London dan New York secara dinamis. Pergeseran musim panas/dingin tidak boleh diasumsikan sebagai jam statis guna mencegah distorsi pola volume.

2.2. Isolasi Zona Rollover Harian (Spread Spike Quarantine)
- Periode rollover broker harian pada pukul 17:00 New York (21:00 atau 22:00 UTC) dikarantina.
- Baris candle pada jam rollover tetap dipertahankan dalam memori deret waktu untuk kontinuitas teknikal, tetapi diberi tanda (*flagged*) sebagai **zona terlarang entri (blacklisted from entry)** untuk mencegah eksekusi di tengah spread abnormal.

2.3. Penyaringan Bad Ticks dan Spurious Outliers
- Setiap bar divalidasi dengan aturan batas rentang: rentang $(High - Low)$ yang melebihi $5 \times \text{ATR}(14)$ tanpa lonjakan volume transaksi riil diidentifikasi sebagai bad tick server broker dan dinormalisasi menggunakan interpolasi median lokal.

---

### BAB 3: REKAYASA FITUR DAN NORMALISASI BEBAS SKALA (STATIONARITY)

3.1. Pencegahan Covariate Shift (Scale-Free Invariance)
Mengingat harga emas bergerak dari $\$1.500$ (tahun 2020) hingga di atas $\$2.600$ (tahun 2024–2026), model dilarang menerima harga absolut. Seluruh fitur harga ditransformasikan menjadi bentuk stasioner:
- Transformasi Harga Relatif:
  $$\tilde{P}_t = \frac{P_t - \text{EMA}_{64}(P_t)}{\text{ATR}_{64}(t)}$$
- Normalisasi Volume Dinamis (Rolling Z-Score 128 bar):
  $$\tilde{V}_t = \frac{V_t - \mu_V(128)}{\sigma_V(128)}$$

3.2. Ekstraksi Fitur Struktur Pasar
Setiap bar waktu $t$ direpresentasikan oleh jendela pengamatan $L = 64$ bar M30 ($t-63$ hingga $t$) dengan 9 channel fitur:
1. Channel 1–4: OHLC yang telah dinormalisasi terhadap EMA dan ATR lokal.
2. Channel 5: Volume Z-score dinamis.
3. Channel 6: Stochastic Momentum Index (SMI) dalam rentang $[-1.0, +1.0]$:
   $$\text{SMI} = 100 \times \frac{\text{EMA}(\text{EMA}(C - M))}{\frac{1}{2} \text{EMA}(\text{EMA}(H - L))}$$
   di mana $M = \frac{1}{2}(H + L)$.
4. Channel 7: Kemiringan sudut (*slope*) dan diferensial Moving Average Ribbon.
5. Channel 8: Jarak harga saat ini terhadap Liquidity Pool terdekat (Fractal Swing High/Low) dibagi ATR.
6. Channel 9: Status Fair Value Gap (FVG) / Order Block yang belum termitigasi (*unmitigated imbalance*).

3.3. Pagar Pengaman Berita Makro (News Blackout Gate)
- Pemanfaatan data kalender makro berstatus High-Impact (NFP, CPI, Keputusan FOMC).
- Variabel biner $B_t \in \{0, 1\}$ menandai interval $T \pm 30$ menit dari waktu rilis. Selama $B_t = 1$, proses inferensi dimatikan secara deterministik (Hard Zero Entry).

---

### BAB 4: PELABELAN TRAJEKTORI REALISTIS PASCA-BIAYA (NET-COST TRIPLE BARRIER)

4.1. Simulasi Barrier Realistis (Net of Fees & Spread)
Setiap momentum historis diuji menggunakan metode Triple Barrier dengan biaya transaksi penuh:
- Barrier Stop Loss (SL): Diletakkan di luar struktur Swing High/Low atau batas Order Block.
- Barrier Take Profit (TP): Ditetapkan pada $+1.0R$ atau $+2.0R$ bersih setelah memperhitungkan spread bursa dan komisi.
- Barrier Waktu: Maksimal $K = 16$ bar M30 (8 jam). Jika harga tidak mencapai TP atau SL dalam batas waktu tersebut, posisi ditutup pada harga pasar.

4.2. Definisi Kelas Target Diskrit
- $a = 0$: HOLD / CHOP (Kondisi pasar tidak memiliki edge, atau hasil bersih trade $\le 0$).
- $a = 1$: BUY Valid dengan rasio $+1.0R$ bersih.
- $a = 2$: BUY Valid dengan rasio $+2.0R$ bersih.
- $a = 3$: SELL Valid dengan rasio $+1.0R$ bersih.
- $a = 4$: SELL Valid dengan rasio $+2.0R$ bersih.

---

### BAB 5: ARSITEKTUR MODEL TUNGGAL (MOMENT-1-LARGE END-TO-END)

5.1. Model Fondasi Tunggal
- Basis Arsitektur: Pretrained Foundation Model `AutonLab/MOMENT-1-large` (Carnegie Mellon University).
- Keputusan Desain: Menolak tumpukan multi-model terpisah guna memangkas akumulasi kesalahan (*error compounding*). MOMENT digunakan secara end-to-end sebagai pengekstraksi fitur dan pengklasifikasi aksi sekaligus.
- Struktur Input Tensor: $(B \times C \times L)$ di mana $B$ adalah ukuran batch, $C = 9$ channel fitur, dan $L = 64$ bar M30.
- Kepala Klasifikasi: Linear classification head dengan normalisasi dropout (0.2) yang langsung memetakan representasi laten MOMENT ke 5 probabilitas aksi diskrit:
  $$P(a_t \mid X_{t-63:t}) \in [0, 1]^5$$

---

### BAB 6: PEMBAGIAN DATA ANTI-LEAKAGE DAN FOCAL LOSS

6.1. Skema Pembagian Data Latih dan Validasi
- **Data In-Sample (4 Tahun Pertama / 80%)**: Digunakan untuk pelatihan, rekayasa fitur, dan penyesuaian bobot.
- **Data Out-of-Sample Sealed Holdout (1 Tahun Terakhir / 20%)**: Terkunci mutlak tanpa akses pra-pemrosesan global untuk menghindari data snooping.
- **Purged & Embargoed Walk-Forward Cross-Validation (5 Lipatan)**:
  - *Purging*: Menghilangkan data latih yang bertabrakan dengan horizon Triple Barrier (16 bar M30).
  - *Embargo*: Menerapkan jeda kosong 48 bar (24 jam) setelah setiap segmen uji untuk memutus korelasi serial autoregresif.

6.2. Penanganan Ketimpangan Kelas (Class-Balanced Focal Loss)
Untuk mencegah fenomena model malas yang selalu memprediksi `HOLD (Class 0)`, fungsi rugi menggunakan Focal Loss dengan bobot penyeimbang kelas:
$$\text{FL}(p_t) = -\alpha_t (1 - p_t)^\gamma \log(p_t)$$
di mana parameter pemfokus $\gamma = 2.0$ meredam gradien dari sampel mudah (sideways pasar yang dominan), dan $\alpha_t$ memprioritaskan momentum kelas 1, 2, 3, dan 4.

6.3. Strategi Fine-Tuning Parameter-Efficient (LoRA)
- Bobot representasi dasar MOMENT dibekukan (*freeze*).
- Low-Rank Adaptation (LoRA, $r=8, \alpha=16$) dipasang pada modul proyeksi atensi ($W_q, W_v$).
- Kepala klasifikasi dilatih penuh menggunakan optimizer AdamW dengan cosine annealing learning rate schedule.

---

### BAB 7: PROTOKOL PELATIHAN BERKALA DAN PEMANTAUAN DRIFT (MLOPS)

7.1. Pelatihan Ulang Bergulir (Quarterly Rolling Retraining)
- Model di-*fine-tune* ulang setiap kuartal (3 bulan) menggunakan jendela data 3 tahun terkini.
- Data usang di atas 3 tahun dikeluarkan dari set aktif untuk mengadaptasi pergeseran rezim makroekonomi.

7.2. Metrik Audit Kesehatan Model
- **Brier Score & Expected Calibration Error (ECE)**: Memastikan probabilitas prediksi terkalibrasi dengan realitas frekuensi kemenangan.
- **Information Coefficient (IC)**: Korelasi rank Spearman antara probabilitas model dan hasil return aktual ($\text{IC} > +0.03$).
- **Population Stability Index (PSI)** pada Embedding Laten: Memantau pergeseran distribusi fitur pasar. Jika $\text{PSI} > 0.25$, bot otomatis masuk ke status isolasi (*fail-safe hold*) hingga model diperbarui.
- **Deflated Sharpe Ratio (DSR)**: Memverifikasi signifikansi performa out-of-sample dengan memperhitungkan uji coba jamak (*multiple testing bias*).

---

### BAB 8: MANAJEMEN RISIKO DAN PENGENDALIAN EKSEKUSI DETERMINISTIK

8.1. Ukuran Posisi Dinamis (Dynamic Lot Sizing)
Ukuran lot dihitung secara deterministik untuk setiap sinyal masuk:
$$\text{Lot Size} = \frac{\text{Equity} \times \text{Risk Fraction}}{\text{SL Distance (Points)} \times \text{Point Value}}$$
dengan batas risiko strictly $1\%$ hingga $2\%$ modal per transaksi.

8.2. Weekly Circuit Breaker
Jika akumulasi drawdown mingguan mencapai batas pertahanan 5%, pembukaan posisi dihentikan hingga pergantian minggu kalender. Batas kerugian mutlak 50% berfungsi sebagai fail-safe struktural yang tidak boleh tersentuh.

8.3. Trailing Breakeven Otomatis
Ketika posisi berjalan mencapai floating profit $+0.7R$, Stop Loss secara otomatis digeser ke harga entry ditambah biaya transaksi (Entry + Spread/Commission) guna memastikan status bebas risiko (*risk-free trade*).

8.4. Friday Close-Out Rule (Proteksi Weekend Gap)
- Pukul 18:00 UTC hari Jumat: Bot dilarang membuka posisi baru.
- Pukul 20:00 UTC hari Jumat: Seluruh posisi mengambang dilikuidasi pada harga pasar untuk menghindari risiko celah harga akhir pekan (*weekend gap*) pada instrumen emas.

---

### BAB 9: AMBANG BATAS KELAYAKAN RISET SEBELUM PENGEMBANGAN APLIKASI

Pengembangan sistem dilarang berpindah ke tahap integrasi perangkat lunak atau antarmuka sebelum memenuhi 3 kriteria kelayakan ilmiah (*Hard Scientific Gates*) pada data Out-of-Sample yang terkunci:

1. **Gate 1 (Konvergensi dan Non-Overfitting)**: Focal Loss pada data validasi konvergen stabil tanpa divergensi training loss.
2. **Gate 2 (Resolusi Bot Malas)**: Model membuktikan kemampuan mendeteksi momentum non-HOLD dengan rasio Precision $\ge 55\%$ dan tidak mengalami class collapse.
3. **Gate 3 (Expectancy Pasca-Biaya Bersih)**: Pada data uji Out-of-Sample 1 tahun terakhir, Profit Factor bersih setelah spread dan komisi bernilai $\ge 1.35$ dengan Maximum Drawdown mingguan tidak pernah menyentuh circuit breaker.

---

### BAB 10: ROADMAP KRONOLOGIS RISET MURNI

1. **Langkah 1**: Pembangunan modul data pipeline historis 5 tahun XAU/USD M30 (Pembersihan DST, Rollover Quarantine, Bad Tick Filter).
2. **Langkah 2**: Pembangunan modul stasionaritas dan rekayasa fitur (Transformasi Scale-Free, SMI, MA Ribbon, Liquidity Swing, FVG).
3. **Langkah 3**: Pembangunan engine pelabelan Triple Barrier Net-Cost & perhitungan bobot Focal Loss.
4. **Langkah 4**: Pembangunan pipeline fine-tuning MOMENT-1-large (LoRA + PEFT).
5. **Langkah 5**: Pelaksanaan Purged Walk-Forward Cross-Validation 5 lipatan.
6. **Langkah 6**: Pembukaan Sealed Holdout Test untuk verifikasi 3 Hard Scientific Gates.
