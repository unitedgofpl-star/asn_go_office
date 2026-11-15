# Bot Telegram instan — Kantor ASN GO (sama seperti Kantor United Go)

1. **Token GitHub:** github.com/settings/personal-access-tokens/new
   - Token name `asn-go-bot`, Expiration 1 tahun
   - Repository access → **Only select repositories** → `asn_go_office`
   - Permissions → Repository permissions → **Actions: Read and write**, **Contents: Read and write**
   - Generate token → salin (diawali `github_pat_...`)
2. **Worker:** dash.cloudflare.com → Workers & Pages → Create → Worker → nama `asn-go-bot` → Deploy
   → Edit code → hapus isi, tempel `worker.js` → Deploy.
3. Worker → Settings → **Variables and Secrets** → Add:
   | Nama | Tipe | Isi |
   |---|---|---|
   | TELEGRAM_BOT_TOKEN | Secret | token @asn_digitalbot dari @BotFather |
   | TELEGRAM_SECRET | Secret | kata sandi bebas, mis. `asngo-rahasia-2026` |
   | GH_TOKEN | Secret | token dari langkah 1 |
   | GH_REPO | Text | `unitedgofpl-star/asn_go_office` |
   | OWNER_CHAT_ID | Text | `759159280` |
   | KANTOR_URL | Text | `https://unitedgofpl-star.github.io/asn_go_office` |
   Klik **Deploy** setelah semua terisi.
4. Buka `https://asn-go-bot.<akun-anda>.workers.dev/setup` → harus muncul "Webhook terpasang ✅".
5. Di Telegram ketik `/bantuan` → bot langsung membalas menu.

Perintah `/bantuan`, `/status`, `/kantor` dijawab langsung (1 detik). Perintah kerja (`/buat`, `/terbit`, tombol ✅🚀🔁🗑, dll.)
dibalas "diterima" seketika, lalu hasilnya datang ±1–3 menit kemudian dari tim di GitHub Actions.
Kirim perintah kerja satu per satu (tunggu hasilnya) agar tidak ada yang terlewat.
