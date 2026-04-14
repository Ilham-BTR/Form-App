# Form-App

Aplikasi Flask untuk form submit survey customer berbasis KC token. Aplikasi ini menyimpan token, nomor customer, kuota harian, dan riwayat submit di PostgreSQL.

## Fitur

- Login user memakai KC token.
- Bearer token disimpan dan dikelola dari halaman admin.
- Nomor customer dibagikan otomatis dari database dan dikunci per KC token.
- Submit survey dengan upload foto transaksi dan screenshot chat.
- Retry otomatis untuk error `401`, `429`, `5xx`, timeout, dan network error.
- Status submit dibedakan menjadi `SUCCESS`, `LIKELY_SUCCESS`, `INVALID`, `FAILED`, dan `PENDING`.
- Nomor invalid/rusak otomatis diganti pada kondisi yang sesuai.
- Kompres gambar di browser sebelum submit jika file lebih besar dari 800 KB.
- Overlay loading dengan timer saat submit berjalan.
- Cache master data BUMO dan KC Area di browser memakai `sessionStorage`.
- Admin dashboard untuk token, database customer, dan live tracking submit.
- Import nomor customer dari Excel atau CSV.
- Logging submit ke `submit.log`.

## Struktur Project

```text
.
|-- app.py
|-- requirements.txt
|-- README.md
`-- templates/
    |-- user_app.html
    |-- token_page.html
    |-- admin_login.html
    |-- admin_dashboard.html
    |-- admin_token_form.html
    |-- admin_customer_db.html
    `-- admin_submit_logs.html
```

## Requirement

- Python 3.10 atau lebih baru
- PostgreSQL
- Dependency Python di `requirements.txt`

## Setup Lokal

1. Buat virtual environment.

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

2. Install dependency.

```powershell
pip install -r requirements.txt
```

3. Buat file `.env` di root project.

```env
APP_ENV=development
FLASK_SECRET_KEY=isi_secret_flask
APP_HMAC_SECRET=isi_hmac_secret_submit
MASTERDATA_HMAC_SECRET=isi_hmac_secret_masterdata
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DBNAME
ADMIN_PAGE_USERNAME=admin
ADMIN_PAGE_PASSWORD=password_admin

DEFAULT_BASE_URL=https://domain-api-kamu
DEFAULT_ENDPOINT=/api/survey-questionnaire-cmkt-v2s/submit
DEFAULT_BUMO_ENDPOINT=/api/bumos
DEFAULT_KC_AREA_ENDPOINT=/api/kc-areas
```

Catatan:

- `MASTERDATA_HMAC_SECRET` opsional. Kalau tidak diisi, aplikasi memakai `APP_HMAC_SECRET`.
- `DEFAULT_BASE_URL`, `DEFAULT_ENDPOINT`, `DEFAULT_BUMO_ENDPOINT`, dan `DEFAULT_KC_AREA_ENDPOINT` punya default di `app.py`, tetapi sebaiknya tetap diset di environment deploy.
- Jangan commit file `.env`, token, password, atau database credential ke GitHub.

4. Jalankan aplikasi.

```powershell
python app.py
```

Default app berjalan di:

```text
http://localhost:5000
```

## Halaman Utama

- `/` - login KC token
- `/user` - form survey customer
- `/logout` - logout user dan lepas nomor reserved
- `/admin/login` - login admin
- `/admin` - dashboard admin
- `/admin/customers` - database nomor customer
- `/admin/submissions` - live tracking submit

## Database

Saat aplikasi start, `init_db()` otomatis membuat tabel jika belum ada:

- `kc_token_usage`
- `valid_kc_tokens`
- `customer_directory`
- `submission_attempts`

Nomor customer disimpan di `customer_directory`. Token KC disimpan di `valid_kc_tokens`.

## Flow Submit

1. User login memakai KC token.
2. Sistem reserve satu nomor customer untuk KC tersebut.
3. User isi form dan upload foto.
4. Browser mengompres gambar jika ukuran file lebih dari 800 KB.
5. Overlay loading muncul dan timer berjalan.
6. Backend submit request ke API tujuan.
7. Jika perlu, backend retry otomatis.
8. Setelah final:
   - `SUCCESS`: nomor ditandai used, kuota naik, form reset, nomor baru diambil.
   - `LIKELY_SUCCESS`: dianggap kemungkinan sudah tercatat, nomor tidak di-invalidasi, form reset, nomor baru diambil.
   - `INVALID`: nomor ditandai invalid/rusak dan diganti.
   - `FAILED`: nomor tetap sama, form tidak di-reset, user bisa upload ulang bukti dan coba submit lagi.

## Retry Policy

- `401`: retry maksimal 3 kali, delay random 1-2 detik.
- `429`: retry maksimal 3 kali, delay random 8-15 detik.
- `5xx`: retry maksimal 3 kali, delay random 2-5 detik.
- Timeout atau network error: retry maksimal 3 kali, delay random 2-5 detik.
- `400`: tidak retry.

Setiap attempt membuat timestamp dan hash baru. Hash lama tidak dipakai ulang.

## Status Submit

- `SUCCESS`: response final `2xx`.
- `LIKELY_SUCCESS`: error retryable lalu response final `400` duplicate, misalnya pesan sudah pernah mengisi form.
- `INVALID`: attempt pertama langsung `400`, atau retry `401` habis dan status akhir tetap `401`.
- `FAILED`: retry habis dan masih gagal di luar rule invalid/likely success.
- `PENDING`: submit attempt sudah dicatat tetapi belum final.

## Image Compression

Kompresi dilakukan di browser sebelum submit:

- File `<= 800 KB`: pakai file asli.
- File `> 800 KB`: resize max 1600 px, fallback 1280 px.
- Output diubah ke JPEG.
- Quality diturunkan bertahap dari 0.95.
- Target hasil 500-800 KB jika memungkinkan.

## Logging

Log ditulis ke:

```text
submit.log
```

Log mencakup:

- attempt ke berapa
- status code tiap attempt
- alasan retry
- delay retry
- final state
- apakah nomor diganti atau tidak

## Deploy

Untuk production, gunakan server WSGI seperti Gunicorn:

```bash
gunicorn app:app
```

Pastikan semua environment variable sudah diset di platform deploy.

## Backup Sebelum Update

Cara paling sederhana:

1. Download ZIP repo dari GitHub.
2. Simpan dengan nama jelas, misalnya:

```text
Form-App-backup-before-update-2026-04-14.zip
```

Cara yang lebih rapi:

```powershell
git checkout main
git pull origin main
git checkout -b backup-before-update-2026-04-14
git push origin backup-before-update-2026-04-14
```

## Railway Night Schedule

Repository ini punya GitHub Actions workflow untuk menghentikan Railway service pada jam 01:00 WIB dan menyalakannya lagi jam 07:00 WIB.

Tambahkan secret berikut di GitHub repository settings:

```text
RAILWAY_TOKEN
RAILWAY_SERVICE_ID
RAILWAY_ENVIRONMENT_ID
```

Isi `RAILWAY_TOKEN` dengan Railway Account token atau Workspace token.

Jadwal workflow memakai UTC:

- `0 18 * * *` = stop jam 01:00 WIB
- `0 0 * * *` = start jam 07:00 WIB

Kalau secret belum diisi, workflow akan skip dan tidak mengubah Railway.

## Catatan Keamanan

- Jangan commit `.env`.
- Jangan commit token, bearer token, password admin, atau connection string database.
- Pastikan repository GitHub tidak berisi secret sebelum deploy.
