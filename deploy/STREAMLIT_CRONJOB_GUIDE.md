# PANDUAN DEPLOY CLOUD 24/7 GRATIS: STREAMLIT + CRON-JOB.ORG
## Flowdev Recurrent Algorithmic Model for Trade Execution (FRAME)

Dokumen ini menjelaskan cara menjalankan **FLOWDEV FRAME** secara **100% Real-Time Online 24 Jam Nonstop di Cloud (Full Gratis Rp 0)** sehingga laptop Anda bebas dimatikan total kapan saja, namun trade real-time tetap berjalan dan tercatat ke Database Audit.

---

## 🏗️ 1. Arsitektur Hybrid Cloud + Desktop

Sistem ini terbagi menjadi 3 pilar yang saling terintegrasi:

1. **Cloud Worker 24/7 (Streamlit Community Cloud):**
   - Menjalankan live engine XAU/USD M30 di server cloud milik Streamlit (Snowflake).
   - Selalu terjaga (*anti-sleep*) berkat kiriman sinyal heartbeat dari `cron-job.org`.
2. **Unified Audit Database (SQLite ACID):**
   - Menyimpan setiap order, eskalasi Kinetic OMS (Micro-BE, Ratchet, Trail), dan inferensi AI.
   - Dapat dievaluasi performanya secara profesional kapan pun seperti laman backtest.
3. **Cockpit Aplikasi Desktop (Laptop):**
   - Menampilkan visualisasi canggih saat laptop Anda nyala.
   - Jika laptop Anda dimatikan, Cloud Web tetap trading di internet!

---

## 🚀 2. Cara Menjalankan Versi Web Secara Lokal di Laptop

Sebelum deploy ke internet, Anda bisa langsung mencobanya di laptop:

1. Klik ganda file launcher:
   [`launch_web_trader.bat`](file:///c:/Ngoding/xau_deep_sniper/launch_web_trader.bat)
2. Browser akan otomatis terbuka ke alamat:
   ```text
   http://localhost:8501
   ```
3. Anda akan melihat 3 mode yang 100% identik dengan aplikasi desktop:
   - **🔴 LIVE REALTIME TRADER:** Chart real-time, Active Position HUD, tombol Panic Close, metrik live, dan log trade.
   - **📊 EVALUASI LIVE TRADES (DATABASE AUDIT):** Evaluasi performa trade live dari database (Equity curve, Win rate, Drawdown underwater chart, OMS breakdown, dan CSV export).
   - **🔬 SIMULASI BACKTEST HISTORIS:** Backtest multi-year (2021-2026), single month, custom range, dual sizing comparison, dan candle inspector.

---

## 🌐 3. Langkah Deploy 24/7 ke Streamlit Cloud (100% Gratis Selamanya)

### Langkah 1: Push Repository ke GitHub
Pastikan folder `xau_deep_sniper` sudah ter-push ke akun GitHub Anda (bisa repository Private atau Public).

### Langkah 2: Hubungkan ke Streamlit Community Cloud
1. Buka [share.streamlit.io](https://share.streamlit.io) dan login menggunakan akun GitHub Anda.
2. Klik tombol **"Create app"** (atau *"New app"*).
3. Isi kolom pengaturan:
   - **Repository:** Pilih repo GitHub Anda (contoh: `ALIFHAIKAL21/bot-trading`).
   - **Branch:** `main` (atau `master`).
   - **Main file path:** Ketik:
     ```text
     src/frame/live/web_app.py
     ```
4. Klik tombol **"Deploy!"**.
5. Tunggu 1–2 menit, web bot Anda akan langsung live di alamat:
   `https://<nama-app-anda>.streamlit.app`

---

## ⏰ 4. Setting Cron-Job.Org (Agar Bot Melek 24/7 Tanpa Pernah Sleep)

Secara default, Streamlit Cloud akan tertidur jika tidak ada pengunjung. Kita menggunakan **cron-job.org** untuk mengirim "ping" agar server cloud tetap aktif selamanya:

1. Buka [cron-job.org](https://cron-job.org) dan buat akun gratis.
2. Di dashboard, klik tombol **"Create Cronjob"**.
3. Isi parameter berikut:
   - **Title:** `FLOWDEV FRAME 24/7 TRADER PING`
   - **URL:** Masukkan link web Streamlit Anda dengan parameter `?cron_ping=1`:
     ```text
     https://<nama-app-anda>.streamlit.app/?cron_ping=1
     ```
   - **Schedule:** Pilih **"Every 1 minute"** (atau *"Every 5 minutes"*).
   - **Request Method:** `GET`
4. Klik **"Save"**.

> [!TIP]
> **Hasilnya:**
> Setiap 1 menit, cron-job.org akan mem-ping web Streamlit Anda. Bot di cloud akan memeriksa harga pasar, mengevaluasi OMS, mengeksekusi order jika ada sinyal M30, mencatat ke Database, dan server tidak akan pernah tidur meskipun laptop Anda dimatikan!

---

## 📱 5. Memantau & Kontrol Trade dari HP Kapan Saja

Setelah tahap di atas selesai:
1. Anda cukup buka link `https://<nama-app-anda>.streamlit.app` dari browser Chrome / Safari di HP Anda.
2. Anda bisa melihat saldo terkini, floating profit/loss, status Stage OMS, dan bahkan menekan tombol **`[⚡ PANIC CLOSE NOW]`** langsung dari layar sentuh HP Anda saat bepergian!
3. Untuk evaluasi, buka tab **`📊 EVALUASI LIVE TRADES (DATABASE AUDIT)`** untuk melihat kurva modal, win rate riil, dan daftar riwayat transaksi dari database.
