# Panduan Self-Host Form-App di PC Rumah (Linux, akses internet)

Panduan ini memindahkan Form-App **sepenuhnya** ke PC rumah berbasis Linux:
aplikasi **dan** database jalan mandiri di PC-mu, dan bisa diakses user lapangan
dari internet.

> Asumsi distro: **Ubuntu / Debian** (pakai `apt`). Kalau pakai distro lain
> (Fedora, Arch, dll), perintah `apt` tinggal disesuaikan dengan package
> manager-mu. Semua langkah dijalankan sebagai user biasa; perintah yang butuh
> akses root memakai `sudo`.

## Arsitektur tujuan

```text
[ User lapangan / HP ]
        |  HTTPS (port 443)
        v
[ Router rumah ]  --port forward 80/443-->  [ PC Linux ]
                                                |
                                          [ Nginx ]  (reverse proxy + SSL)
                                                |  http://127.0.0.1:5000
                                          [ Gunicorn -> app.py ]
                                                |
                                          [ PostgreSQL lokal ]
```

Yang berubah dari setup lama:

- **Hosting app:** dari Railway/Vercel -> PC rumah (Gunicorn + Nginx).
- **Database:** dari Supabase -> PostgreSQL lokal di PC.
- **Foto:** tetap **tidak disimpan** app (langsung diteruskan ke API Mobil 1
  lalu temp file dihapus). Self-host tidak mengubah ini.

---

## 0. Prasyarat

- PC Linux yang bisa **nyala 24/7** (kalau PC mati, app mati — tidak ada
  auto-recovery seperti Railway).
- Akses ke router rumah (untuk port forwarding).
- Koneksi internet dengan, idealnya, **IP publik** (lihat Bagian 7 soal CGNAT).
- Sebuah domain (opsional tapi sangat disarankan untuk HTTPS). Bisa domain
  berbayar atau subdomain DDNS gratis (DuckDNS, dll).
- Akses ke project Supabase lama (untuk export data).

---

## 1. Install dependency sistem

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip \
                    postgresql postgresql-contrib \
                    nginx git ufw
```

Cek versi Python (butuh 3.10+):

```bash
python3 --version
```

---

## 2. Ambil kode aplikasi

```bash
cd ~
git clone https://github.com/ilham-btr/form-app.git Form-App
cd Form-App
```

> Ganti URL kalau nama repo/owner berbeda. Repo ini privat, jadi siapkan
> Personal Access Token GitHub saat diminta password.

Buat virtual environment dan install dependency Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Siapkan PostgreSQL lokal

Buat database dan user khusus untuk app:

```bash
sudo -u postgres psql
```

Di dalam prompt `psql`, jalankan (ganti password dengan yang kuat):

```sql
CREATE DATABASE formapp;
CREATE USER formapp_user WITH PASSWORD 'ganti_password_kuat';
GRANT ALL PRIVILEGES ON DATABASE formapp TO formapp_user;
\c formapp
GRANT ALL ON SCHEMA public TO formapp_user;
\q
```

Connection string-mu nanti jadi:

```text
postgresql://formapp_user:ganti_password_kuat@127.0.0.1:5432/formapp
```

---

## 4. Migrasi data dari Supabase

Ada dua cara. Pilih salah satu.

### Cara A — Pindah data lama (disarankan kalau data lama mau dipertahankan)

Ambil connection string Supabase dari dashboard:
**Project Settings -> Database -> Connection string (URI)**.

Dump dari Supabase lalu restore ke Postgres lokal:

```bash
# 1) Dump semua data dari Supabase (hanya data + skema tabel app)
pg_dump "postgresql://postgres:PASS@db.xxxx.supabase.co:5432/postgres" \
  --no-owner --no-privileges \
  --table=kc_token_usage \
  --table=valid_kc_tokens \
  --table=customer_directory \
  --table=submission_attempts \
  --table=bumo_master \
  --table=kc_area_master \
  --table=team_leaders \
  --table=team_leader_kc_access \
  -f supabase_dump.sql

# 2) Restore ke database lokal
psql "postgresql://formapp_user:ganti_password_kuat@127.0.0.1:5432/formapp" \
  -f supabase_dump.sql
```

> Simpan `supabase_dump.sql` baik-baik lalu hapus setelah yakin restore sukses —
> isinya termasuk bearer token dan nomor customer.

### Cara B — Mulai dari kosong

Lewati langkah dump. App akan otomatis bikin semua tabel lewat `init_db()` saat
pertama kali start (lihat `app.py`). Cocok kalau mau mulai bersih.

---

## 5. Konfigurasi `.env`

Buat file `.env` di folder project (jangan pernah di-commit — sudah ada di
`.gitignore`):

```bash
nano ~/Form-App/.env
```

Isi (sesuaikan nilainya):

```env
APP_ENV=production
FLASK_SECRET_KEY=isi_secret_acak_panjang
APP_HMAC_SECRET=isi_hmac_secret_submit
MASTERDATA_HMAC_SECRET=isi_hmac_secret_masterdata
DATABASE_URL=postgresql://formapp_user:ganti_password_kuat@127.0.0.1:5432/formapp
ADMIN_PAGE_USERNAME=admin
ADMIN_PAGE_PASSWORD=password_admin_kuat

DEFAULT_BASE_URL=https://domain-api-mobil1
DEFAULT_ENDPOINT=/api/survey-questionnaire-cmkt-v2s/submit
DEFAULT_BUMO_ENDPOINT=/api/bumos
DEFAULT_KC_AREA_ENDPOINT=/api/kc-areas
RESERVED_PHONE_TIMEOUT_MINUTES=120
PORT=5000
```

> Untuk `FLASK_SECRET_KEY` bisa generate acak:
> `python3 -c "import secrets; print(secrets.token_hex(32))"`

Uji coba jalan manual dulu:

```bash
cd ~/Form-App
source .venv/bin/activate
python3 app.py
```

Buka `http://localhost:5000` dari PC itu sendiri. Kalau halaman login token
muncul, lanjut. Hentikan dengan `Ctrl+C`.

---

## 6. Jalankan permanen dengan systemd + Gunicorn

Buat service supaya app jalan terus dan otomatis restart kalau crash / PC reboot.

```bash
sudo nano /etc/systemd/system/formapp.service
```

Isi (ganti `NAMA_USER` dengan username Linux-mu, cek dengan `whoami`):

```ini
[Unit]
Description=Form-App Gunicorn
After=network.target postgresql.service

[Service]
User=NAMA_USER
WorkingDirectory=/home/NAMA_USER/Form-App
Environment="PATH=/home/NAMA_USER/Form-App/.venv/bin"
ExecStart=/home/NAMA_USER/Form-App/.venv/bin/gunicorn \
          --workers 1 --threads 8 --timeout 180 \
          --bind 127.0.0.1:5000 app:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

> `--workers 1 --threads 8` sengaja disamakan dengan config Railway lamamu
> (`railway.json`). App ini punya scheduler/state internal, jadi **jangan**
> menaikkan jumlah worker tanpa pengujian.

Aktifkan:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now formapp
sudo systemctl status formapp     # pastikan "active (running)"
```

Lihat log kalau ada masalah: `journalctl -u formapp -f`

---

## 7. Buka ke internet

### 7a. Nginx reverse proxy

```bash
sudo nano /etc/nginx/sites-available/formapp
```

Isi (ganti `domain-kamu.com` dengan domain/DDNS-mu):

```nginx
server {
    listen 80;
    server_name domain-kamu.com;

    client_max_body_size 20M;   # foto upload bisa beberapa MB

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;
    }
}
```

Aktifkan dan reload:

```bash
sudo ln -s /etc/nginx/sites-available/formapp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 7b. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'   # buka port 80 + 443
sudo ufw enable
```

### 7c. Domain / DDNS

IP rumah biasanya **berubah-ubah** (dinamis). Pakai salah satu:

- **Domain berbayar** + update A record ke IP publikmu, atau
- **DDNS gratis** seperti DuckDNS — kasih subdomain (mis. `mobil1.duckdns.org`)
  yang otomatis ikut IP rumahmu yang berubah.

Cek IP publikmu: `curl ifconfig.me`

> **Penting — CGNAT:** sebagian ISP (terutama paket rumahan/seluler) tidak
> memberi IP publik asli, jadi port forwarding **tidak akan jalan**. Cek dengan
> bandingkan `curl ifconfig.me` dengan IP WAN di halaman admin router. Kalau
> beda, kamu kena CGNAT — solusinya minta IP publik ke ISP, atau pakai tunnel
> seperti **Cloudflare Tunnel** (gratis, juga sekalian beri HTTPS dan
> menyembunyikan IP rumah). Cloudflare Tunnel sering jadi opsi terbaik untuk
> host dari rumah.

### 7d. Port forwarding di router

Di panel admin router, arahkan:

- Port eksternal **80** -> IP lokal PC port **80**
- Port eksternal **443** -> IP lokal PC port **443**

Set juga **IP statis lokal** (DHCP reservation) untuk PC supaya IP-nya tidak
berganti.

### 7e. HTTPS gratis (Let's Encrypt)

Setelah domain mengarah ke rumahmu dan port 80 terbuka:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d domain-kamu.com
```

Certbot otomatis pasang sertifikat + redirect ke HTTPS, dan perpanjang sendiri.

> Kalau pakai **Cloudflare Tunnel**, langkah 7d dan 7e tidak perlu — HTTPS dan
> akses ditangani Cloudflare.

---

## 8. Backup otomatis (tujuan awalmu)

Di server sendiri, backup database jadi mudah: dump berkala + simpan ke disk
(dan, kalau mau, sync ke OneDrive). Sesuai pilihanmu: **CSV/zip, sebulan sekali**.

Buat skrip backup:

```bash
mkdir -p ~/formapp-backups
nano ~/Form-App/backup.sh
```

Isi:

```bash
#!/usr/bin/env bash
set -e
STAMP=$(date +%Y-%m-%d)
OUT=~/formapp-backups
DB="postgresql://formapp_user:ganti_password_kuat@127.0.0.1:5432/formapp"

# Dump penuh (format custom, paling aman untuk restore)
pg_dump "$DB" -Fc -f "$OUT/formapp_$STAMP.dump"

# (Opsional) export tiap tabel ke CSV lalu zip
TMP=$(mktemp -d)
for t in kc_token_usage valid_kc_tokens customer_directory submission_attempts \
         bumo_master kc_area_master team_leaders team_leader_kc_access; do
  psql "$DB" -c "\copy $t TO '$TMP/$t.csv' CSV HEADER"
done
zip -j "$OUT/formapp_csv_$STAMP.zip" "$TMP"/*.csv
rm -rf "$TMP"

# Simpan hanya 12 backup terakhir
ls -1t "$OUT"/formapp_*.dump | tail -n +13 | xargs -r rm
ls -1t "$OUT"/formapp_csv_*.zip | tail -n +13 | xargs -r rm
```

Jadikan executable:

```bash
chmod +x ~/Form-App/backup.sh
```

Jadwalkan **sebulan sekali** (tanggal 1, jam 01:00) via cron:

```bash
crontab -e
```

Tambahkan baris:

```cron
0 1 1 * * /home/NAMA_USER/Form-App/backup.sh >> /home/NAMA_USER/formapp-backups/backup.log 2>&1
```

### Sync ke OneDrive (opsional)

Untuk dorong hasil backup ke OneDrive Personal, cara paling sederhana di Linux
adalah pakai **rclone**:

```bash
sudo apt install -y rclone
rclone config        # buat remote bernama "onedrive" (ikuti wizard, pilih OneDrive Personal)
```

Lalu tambahkan baris ini di akhir `backup.sh`:

```bash
rclone copy "$OUT" onedrive:FormAppBackups
```

> Restore dari backup: `pg_restore -d "$DB" --clean formapp_TANGGAL.dump`

---

## 9. Checklist keamanan & maintenance

- [ ] Password admin (`ADMIN_PAGE_PASSWORD`) dan password DB **kuat & unik**.
- [ ] `.env` **tidak** ikut ter-commit (sudah di `.gitignore`).
- [ ] Hanya port 80/443 yang dibuka ke internet; **jangan** ekspos 5432
      (PostgreSQL) atau 5000 ke publik.
- [ ] PostgreSQL hanya listen di `127.0.0.1` (default Ubuntu sudah begitu).
- [ ] HTTPS aktif (jangan kirim data customer lewat HTTP polos).
- [ ] Update rutin: `sudo apt update && sudo apt upgrade`.
- [ ] PC pakai UPS / minimal sadar bahwa mati listrik = app down.
- [ ] Backup diuji restore-nya minimal sekali (backup yang tak pernah diuji =
      bukan backup).
- [ ] Pertimbangkan **Cloudflare Tunnel** untuk menyembunyikan IP rumah dan
      mengurangi paparan serangan.

---

## 10. Update aplikasi ke depan

```bash
cd ~/Form-App
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart formapp
```

---

## Ringkasan perintah cepat

```bash
sudo systemctl status formapp      # cek app
sudo systemctl restart formapp     # restart app
journalctl -u formapp -f           # lihat log app
sudo systemctl reload nginx        # reload nginx
~/Form-App/backup.sh               # backup manual
```
