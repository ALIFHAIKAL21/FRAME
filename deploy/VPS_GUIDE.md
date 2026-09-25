# Panduan Menjalankan Bot 24/7 di Cloud VPS (Laptop Bisa Dimatikan)

Agar bot trading Anda bisa berjalan **non-stop 24 jam sehari, 7 hari seminggu (24/7)** tanpa henti meskipun laptop Anda mati, ditutup, atau kehilangan koneksi internet, bot harus ditaruh di **VPS (Virtual Private Server / Cloud Server)**.

---

## 1. Memilih Penyedia VPS (Murah & Cepat)

Pilih VPS dengan OS **Ubuntu 22.04 atau 24.04 LTS**:

| Provider | Lokasi Server Rekomendasi | Biaya Estimasi | Catatan |
| :--- | :--- | :--- | :--- |
| **DigitalOcean** | Singapura (SGP1) | ~$4 - $6 / bulan | Paling mudah, koneksi ke Binance sangat cepat (< 10ms). |
| **Hetzner Cloud** | Jerman / Finlandia | ~€3.79 / bulan | Performa CPU tinggi, sangat murah. |
| **AWS Lightsail** | Singapura | ~$3.50 - $5 / bulan | Terintegrasi dengan ekosistem AWS. |
| **IDCloudHost / DomaiNesia** | Indonesia / SG | ~Rp 50.000 / bulan | Pembayaran mudah via QRIS / Bank Transfer. |
| **Oracle Cloud (Free Tier)** | Singapura / Global | **GRATIS** | Ada paket Always Free selamanya jika akun disetujui. |

*Spesifikasi minimum yang dibutuhkan: 1 vCPU, 1 GB RAM, 20 GB SSD.*

---

## 2. Langkah Setup 5 Menit di VPS

Setelah Anda menyewa VPS dan mendapatkan **IP Address** serta **Password/SSH Key**:

### Langkah 1: Hubungkan ke VPS dari Laptop Anda
Buka Terminal (PowerShell / Command Prompt) di laptop:
```powershell
ssh root@<IP_ADDRESS_VPS_ANDA>
```
*(Masukkan password VPS Anda).*

### Langkah 2: Copy / Clone Folder Bot Trading ke VPS
Di dalam terminal VPS:
```bash
# Clone dari repository git Anda atau upload folder:
git clone <URL_REPO_ANDA> xau_deep_sniper
cd xau_deep_sniper
```
*(Atau upload folder proyek via SFTP / FileZilla / WinSCP).*

### Langkah 3: Jalankan Auto-Setup 1 Perintah
Cukup jalankan script otomatis yang sudah kami sediakan:
```bash
chmod +x deploy/setup_vps.sh
./deploy/setup_vps.sh
```

Script ini otomatis:
1. Menginstal Python 3.10 dan semua library quant (`ccxt`, `torch`, `lightgbm`, `streamlit`, dll).
2. Mendaftarkan bot ke sistem Linux `systemd` dengan fitur **Auto-Restart**.
3. Menjalankan **Scalper 5 Menit** di background.
4. Menjalankan **Dashboard Streamlit** di background.

---

## 3. Opsi Alternatif: Menggunakan Docker (1 Perintah)

Jika VPS Anda sudah terinstal Docker:
```bash
# Build dan jalankan bot + dashboard di background:
docker compose up -d --build
```
Untuk melihat log:
```bash
docker compose logs -f
```

---

## 4. Cara Memantau Bot dari HP / Browser Laptop yang Sudah Dimatikan

Setelah bot jalan di VPS, **laptop Anda boleh langsung dimatikan!**

Untuk memantau kinerja, order yang terbuka, dan grafik modal:
1. Buka browser di HP atau laptop mana saja.
2. Masukkan URL:
   ```text
   http://<IP_ADDRESS_VPS_ANDA>:8502
   ```
3. Dashboard Streamlit akan langsung terbuka secara realtime:
   - Melihat saldo kas & nilai BTC yang sedang di-hold.
   - Melihat order BUY/SELL yang dieksekusi secara otomatis saat Anda tidur.
   - Melihat prediksi probabilitas $P(\text{Long})$ dan alasan aksi bot.

---

## 5. Perintah Berguna di VPS (Maintenance)

```bash
# Melihat status bot scalper:
sudo systemctl status quant-scalper.service

# Melihat log transaksi langsung (live stream):
tail -f logs/scalper_stdout.log

# Menghentikan bot sementara:
sudo systemctl stop quant-scalper.service

# Menjalankan kembali bot:
sudo systemctl start quant-scalper.service

# Restart bot:
sudo systemctl restart quant-scalper.service
```
