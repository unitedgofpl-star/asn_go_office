# 🏢 Kantor Virtual @asn_go_digitals

Ini kantor berisi 8 karyawan AI yang menjalankan akun Instagram dan Facebook Page **ASN GO Digitals**
dengan biaya **Rp0/bulan**. Anda cukup memerintah mereka lewat Telegram.

| Karyawan | Tugas |
|---|---|
| 👔 **Pak Kepala** | Manajer: membaca perintah Telegram dan membagi tugas |
| 🔎 **Mbak Riset** | Memantau berita 7 hari terakhir (ASN, dana desa, SPBE, AI) via Google News RSS |
| ✍️ **Bu Naskah** | Menulis carousel + caption + hashtag sesuai pilar & format harian |
| 🛡 **Pak Verifikator** | Mengecek klaim regulasi/angka, etika ASN, EYD, dan memberi skor risiko |
| 🎨 **Mas Desain** | Merender 5–10 slide 1080×1350 (navy, merah-putih, motif kawung) |
| 📣 **Mbak Humas** | Menerbitkan ke Instagram & Facebook Page sesuai jadwal |
| 💰 **Bang Cuan** | Menyelipkan CTA produk lynk.id dan menulis copy promo |
| 📊 **Kak Analis** | Membuat laporan mingguan berisi postingan terbaik dan rekomendasi |

## Alur kerja harian
```
07:00 WIT  Tim membuat draft → pratinjau carousel dikirim ke Telegram Anda
           [✅ Setujui] [🚀 Terbit sekarang] [🔁 Tulis ulang] [🗑 Tolak]
19:00 WIT  Mbak Humas menerbitkan draft yang sudah disetujui ke IG + FB
Senin      Kak Analis mengirim laporan performa mingguan
```
Kalender konten (bisa diubah di `config.yaml`): Senin AI-tutorial • Selasa Desa-tutorial • Rabu ASN-listicle •
Kamis Contekan Prompt • Jumat Desa-listicle • Sabtu Mitos vs Fakta ASN • Minggu soft-selling produk.

## Gaya visual & virtual influencer Cicilia
Setiap carousel mengikuti gaya media berita:
1. **Cover dramatis:** Cicilia di tengah, latar merah dengan sinar dan efek cahaya tepi, judul putih dalam kotak marun bertepi tetes.
2. **Slide daftar bernomor:** latar abu, kartu putih, lingkaran nomor merah, ikon bulat di kanan, dan catatan kaki "i".
3. **Slide detail:** satu slide untuk setiap poin penting (kotak "SALIN PROMPT" muncul otomatis untuk format prompt).
4. **Penutup:** Cicilia mempromosikan produk lynk.id.

**Mode foto Cicilia:**
| Mode | Cara kerja | Biaya |
|---|---|---|
| Gratis (default) | Pose dari `assets/influencer/*.png` (latar sudah dihapus) ditempel ke latar dramatis | Rp0 |
| Gemini (opsional) | Isi secret `IMAGE_MODE` = `gemini` + aktifkan billing di AI Studio. Setiap cover = foto baru Cicilia sesuai topik, memakai `referensi_wajah.jpg` | ± Rp650/gambar (± Rp20 rb/bulan) |

Menambah pose gratis: hapus latar foto (mis. remove.bg), simpan PNG di `assets/influencer/`, lalu tambahkan namanya di `config.yaml → influencer.poses`.
Persona, gaya bahasa, arahan foto, dan label AI diatur di `config.yaml → influencer`.

---

## Setup (±45 menit, cukup sekali)

### 1. Buat repo GitHub (gratis)
1. Buat akun di github.com lalu **New repository** → nama `asn-go-office` → **Public**.
   Repo harus Public karena Instagram mengambil gambar dari URL publik. Selain itu, GitHub Actions gratis tanpa batas untuk repo publik.
   Semua kunci API disimpan di *Secrets* yang terenkripsi, jadi tidak ikut terlihat publik.
2. Upload seluruh isi folder ini (drag & drop di halaman repo, atau `git push`).

### 2. Otak AI gratis
- **Gemini** (utama): buka https://aistudio.google.com/apikey → *Create API key*.
- **Groq** (cadangan, opsional): buka https://console.groq.com/keys → *Create API Key*.

### 3. Bot Telegram
1. Chat **@BotFather** → `/newbot` → beri nama, mis. `Kantor ASN GO` → salin **token**.
2. Chat bot Anda, ketik `/start`, lalu buka `https://api.telegram.org/bot<TOKEN>/getUpdates`
   dan salin angka `"chat":{"id": ...}`. Itulah **TELEGRAM_CHAT_ID**. Hanya chat ID ini yang bisa memerintah kantor.
3. (Opsional) Di BotFather ketik `/setcommands` lalu tempel:
```
buat - Buat carousel baru (topik opsional)
buat_promo - Carousel soft-selling produk
ide - 10 ide konten
antrian - Daftar draft
setuju - Setujui draft
terbit - Terbitkan sekarang
revisi - Revisi draft dengan catatan
tolak - Buang draft
promo - Copy promosi WA/Story
produk - Daftar produk lynk.id
laporan - Laporan performa
status - Status karyawan
otomatis - Mode terbit otomatis on/off
bantuan - Menu bantuan
```

### 4. Instagram + Facebook Page (Meta Graph API, gratis)
1. Ubah @asn_go_digitals menjadi akun **Profesional (Bisnis/Kreator)**, lalu hubungkan ke **Facebook Page** ASN GO Digitals
   (Pengaturan IG → Pusat Akun, atau Pengaturan Page → Akun tertaut).
2. Buka https://developers.facebook.com → *My Apps* → **Create App** → tipe *Business*.
3. Buka **Graph API Explorer** → pilih app Anda → *Get User Access Token* dengan izin:
   `pages_show_list, pages_read_engagement, pages_manage_posts, instagram_basic, instagram_content_publish, instagram_manage_insights, business_management`.
4. Tukar token tersebut menjadi **long-lived** di *Access Token Debugger* → *Extend Access Token*.
5. Di Explorer, panggil `me/accounts` dengan token long-lived tadi. Salin `access_token` milik Page (**META_PAGE_TOKEN**, tidak kedaluwarsa)
   dan `id` (**FB_PAGE_ID**).
6. Panggil `<FB_PAGE_ID>?fields=instagram_business_account` lalu salin id-nya sebagai **IG_USER_ID**.

> Untuk dipakai di akun Anda sendiri, app tidak perlu *App Review*; mode Development sudah cukup selama Anda admin app dan Page-nya.

### 5. Isi GitHub Secrets
Buka repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Nama | Isi |
|---|---|
| `GEMINI_API_KEY` | dari langkah 2 |
| `GROQ_API_KEY` | opsional |
| `TELEGRAM_BOT_TOKEN` | dari BotFather |
| `TELEGRAM_CHAT_ID` | chat ID Anda |
| `META_PAGE_TOKEN` | token Page |
| `FB_PAGE_ID` | id Page |
| `IG_USER_ID` | id Instagram bisnis |
| `IMAGE_MODE` | opsional: `gemini` |

Lalu buka **Settings → Actions → General → Workflow permissions** dan pilih **Read and write**.

### 6. Atur produk & gaya
Edit `config.yaml`:
- ganti `USERNAME_ANDA` dengan link lynk.id Anda (Generator Naskah Dinas, dll.);
- tambah produk baru di bagian `products:`;
- ubah warna, jam posting, kalender mingguan, atau sumber riset sesuai kebutuhan.

### 7. Uji coba
Buka tab **Actions** → *Kantor Virtual ASN GO* → **Run workflow** → mode `daily`.
Dalam 1–2 menit pratinjau carousel masuk ke Telegram. Tekan **✅ Setujui**.

### 8. Kantor 3D (dashboard live)
Buka **Settings → Pages** → Source `main` / folder `/docs` → Save.
Kantor 3D akan tampil di `https://<username>.github.io/asn-go-office/?repo=<username>/asn-go-office`
dan menampilkan status setiap karyawan secara live dari `data/state.json`.

---

## Catatan penting
- **Mode persetujuan aktif secara default.** Untuk niche pemerintahan, satu kesalahan nomor regulasi bisa merusak kredibilitas.
  Setelah Anda percaya pada hasilnya, ketik `/otomatis on`.
- **Kecepatan respons bot:** dalam mode gratis standar, perintah dibaca setiap ±15 menit (jadwal GitHub kadang molor 5–10 menit).
  Kalau ingin balasan ±1 menit, pasang `cloudflare/worker.js` (gratis); panduannya ada di file tersebut.
- **Batas gratis:** Gemini free tier cukup untuk ±20–40 carousel per hari. Instagram API membatasi 50 posting per 24 jam.
- **Batas yang tidak bisa diatasi tanpa biaya:** auto-reply DM/komentar butuh server yang selalu menyala dan App Review Meta,
  jadi belum termasuk. Gunakan `/promo` untuk menyiapkan teks balasan cepat.
- Hapus folder `public/` lama sesekali (gambar sudah tersimpan di IG/FB) agar repo tetap ringan.

## Struktur
```
config.yaml              ← pusat pengaturan (brand, pilar, jadwal, produk)
office/main.py           ← Pak Kepala + router perintah Telegram
office/agents/*.py       ← para karyawan
office/llm.py            ← Gemini → Groq fallback
office/meta.py           ← Instagram & Facebook Graph API
office/telegram.py       ← Telegram Bot API
docs/index.html          ← kantor virtual 3D
.github/workflows/       ← jadwal kerja otomatis
cloudflare/worker.js     ← (opsional) mode instan
```
Tes desain tanpa API: `pip install -r requirements.txt && python -m office.main demo`
