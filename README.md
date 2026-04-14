# Form-App

Aplikasi Flask untuk form submit survey customer berbasis KC token. Aplikasi ini menyimpan token, nomor customer, kuota harian, dan riwayat submit di PostgreSQL.

## Fitur

- Login user memakai KC token.
- Bearer token disimpan dan dikelola dari halaman admin.
- Nomor customer dibagikan otomatis dari database dan dikunci per KC token.
- Submit survey dengan upload foto transaksi dan screenshot chat.
- Kompres foto di browser dengan target sekitar 500 KB per file sebelum submit.
- Retry dilakukan manual oleh user jika submit gagal.
- Status submit dibedakan menjadi `SUCCESS`, `LIKELY_SUCCESS`, `INVALID`, `FAILED`, dan `PENDING`.
- Nomor invalid/rusak otomatis diganti pada kondisi yang sesuai.
- Overlay loading dengan timer saat submit berjalan.
- Cache master data BUMO dan KC Area di browser memakai `sessionStorage`.
- Admin dashboard untuk token, database customer, dan live tracking submit.
- Import detail KC token dari Excel atau CSV.
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
RESERVED_PHONE_TIMEOUT_MINUTES=120
```

Catatan:

- `MASTERDATA_HMAC_SECRET` opsional. Kalau tidak diisi, aplikasi memakai `APP_HMAC_SECRET`.
- `RESERVED_PHONE_TIMEOUT_MINUTES` opsional. Default `120` menit untuk melepas nomor yang terlalu lama reserved tanpa submit.
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

## Import Detail KC Token

Dari halaman `/admin`, gunakan menu `Import Detail Token`.
Gunakan `Export Detail Token` untuk download CSV berisi data token yang bisa diimport ulang.

Format file `.xlsx` atau `.csv`:

- Header wajib: `kc_name`, `bearer_token`, `daily_limit`, `is_active`
- Header opsional: `token_area`, `kc_token`, `sudah_terpakai`
- Jika `kc_token` kosong atau tidak ada, aplikasi membuat KC token otomatis dengan format `KC-xxxxxxxxxxxxxxxx`.
- Jika `kc_token` sudah ada, nama KC, area, bearer token, limit harian, dan status aktif/nonaktif akan di-update.
- `sudah_terpakai` mengisi pemakaian token untuk tanggal WIB hari ini jika kolomnya ada di file.
- File export berisi bearer token asli, jadi simpan file tersebut dengan hati-hati.

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
4. Overlay loading muncul dan timer berjalan.
5. Backend submit request ke API tujuan satu kali.
6. Jika gagal, user bisa retry manual dengan submit ulang.
7. Setelah final:
   - `SUCCESS`: nomor ditandai used, kuota naik, form reset, nomor baru diambil.
   - `LIKELY_SUCCESS`: dianggap kemungkinan sudah tercatat, nomor tidak di-invalidasi, form reset, nomor baru diambil.
   - `INVALID`: nomor ditandai invalid/rusak dan diganti.
   - `FAILED`: nomor tetap sama, form tidak di-reset, user bisa upload ulang bukti dan coba submit lagi.

## Retry Policy

- Backend tidak melakukan retry otomatis.
- Setiap klik submit membuat satu request ke API tujuan.
- Jika submit gagal, nomor tetap sama untuk retry manual, kecuali response `400` non-duplicate yang dianggap invalid.
- `401` dianggap masalah bearer token atau HMAC secret, bukan nomor invalid.

Setiap submit membuat timestamp dan hash baru. Hash lama tidak dipakai ulang.

## Status Submit

- `SUCCESS`: response final `2xx`.
- `LIKELY_SUCCESS`: response `400` duplicate, misalnya pesan sudah pernah mengisi form.
- `INVALID`: response `400` non-duplicate.
- `FAILED`: gagal di luar rule invalid/likely success.
- `PENDING`: submit attempt sudah dicatat tetapi belum final.

## Upload Gambar

- Browser mencoba kompres foto transaksi dan screenshot chat di sisi client dengan target sekitar `500 KB` per file.
- Jika file sudah `500 KB` atau lebih kecil, kompres dilewati.
- Jika kompres gagal atau terlalu lama, file asli tetap dikirim agar submit tidak stuck.
- Backend/Railway tidak melakukan kompres gambar.

## Logging

Log ditulis ke:

```text
submit.log
```

Log mencakup:

- attempt ke berapa
- status code tiap attempt
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

## Catatan Keamanan

- Jangan commit `.env`.
- Jangan commit token, bearer token, password admin, atau connection string database.
- Pastikan repository GitHub tidak berisi secret sebelum deploy.
