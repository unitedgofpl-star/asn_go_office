"""Cek kesehatan kantor — jalankan dari tab Actions → Run workflow → mode: cek.
Hasilnya tampil di log Actions (dan dikirim ke Telegram jika bisa)."""
import html

import requests

from . import telegram
from .core import env

OK, BAD, WARN = "✅", "❌", "⚠️"


def run(cfg, state):
    out = []

    def say(icon, msg):
        out.append(f"{icon} {msg}")
        print(f"{icon} {msg}")

    print("\n================ CEK KESEHATAN KANTOR ================\n")
    # 1. Secrets
    for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GEMINI_API_KEY", "META_PAGE_TOKEN", "IG_USER_ID", "FB_PAGE_ID"):
        v = env(name)
        say(OK if v else BAD, f"Secret {name}: {'terisi' if v else 'KOSONG — isi di Settings → Secrets → Actions'}")

    # 2. Token bot
    tok = telegram.bot_token()
    if tok:
        import re as _re
        if not _re.fullmatch(r"\d{6,}:[A-Za-z0-9_-]{30,}", tok):
            say(BAD, f"Format TELEGRAM_BOT_TOKEN salah (panjang {len(tok)} karakter). Token yang benar berbentuk "
                     "angka:huruf, contoh 7712345678:AAH... (±46 karakter). Salin dari @BotFather → /mybots → API Token.")
        me = telegram.raw("getMe")
        if me.get("ok"):
            say(OK, f"Token bot valid: @{me['result']['username']}")
        else:
            say(BAD, f"Token bot DITOLAK Telegram ({me.get('description')}). Salin ulang token dari @BotFather tanpa spasi.")

        # 3. Webhook (webhook aktif = polling tidak menerima pesan)
        wh = telegram.raw("getWebhookInfo")
        url = (wh.get("result") or {}).get("url")
        if url:
            say(OK, f"Bot instan (Cloudflare Worker) aktif: {url}")
        else:
            say(WARN, "Cloudflare Worker belum terpasang — bot hanya membalas saat Run workflow mode poll. Lihat cloudflare/PANDUAN.md")

        # 4. Chat ID yang terlihat (bantu menemukan TELEGRAM_CHAT_ID)
        ups = telegram.raw("getUpdates", {"offset": -10, "timeout": 0})
        seen = {}
        for u in ups.get("result", []) or []:
            m = u.get("message") or (u.get("callback_query") or {}).get("message") or {}
            ch = m.get("chat") or {}
            if ch.get("id"):
                seen[str(ch["id"])] = ch.get("first_name") or ch.get("title") or ""
        if seen:
            say(OK, "Chat yang baru mengirim pesan ke bot: " + ", ".join(f"{k} ({v})" for k, v in seen.items()))
            if env("TELEGRAM_CHAT_ID") and env("TELEGRAM_CHAT_ID") not in seen:
                say(WARN, f"TELEGRAM_CHAT_ID={env('TELEGRAM_CHAT_ID')} tidak cocok dengan chat di atas. Ganti secret-nya dengan angka di atas.")

        # 5. Kirim pesan uji
        cid = env("TELEGRAM_CHAT_ID")
        if cid:
            r = telegram.raw("sendMessage", {"chat_id": cid, "text": "🏢 Tes dari Kantor ASN GO: bot tersambung! Ketik /bantuan"})
            if r.get("ok"):
                say(OK, "Pesan uji TERKIRIM ke Telegram Anda.")
            else:
                say(BAD, f"Gagal kirim ke chat {cid}: {r.get('description')}. "
                         "Pastikan Anda sudah menekan START di bot dan CHAT_ID benar (angka saja, tanpa tanda kutip).")

    # 6. Gemini
    if env("GEMINI_API_KEY"):
        try:
            from . import llm
            jawab = llm._gemini("Jawab satu kata: OK", "Asisten singkat.", False)
            say(OK, f"Gemini berfungsi (jawaban: {jawab.strip()[:20]})")
        except Exception as e:
            say(BAD, f"Gemini: {str(e)[:200]}")

    # 7. Meta
    if env("META_PAGE_TOKEN"):
        try:
            v = env("GRAPH_VERSION", "v21.0")
            from . import meta
            name, kind = meta.token_info()
            if name is None:
                say(BAD, f"Token Meta: {kind}")
            elif kind == "Page":
                say(OK, f"Token Meta: token Page '{name}' (permanen)")
            else:
                pt = meta._token()
                ok = pt != env("META_PAGE_TOKEN").strip().strip('"')
                say(WARN if ok else BAD, f"Token Meta milik pengguna '{name}'. "
                    + ("Token Page diambil otomatis (berfungsi, tapi ikut kedaluwarsa ±60 hari; sebaiknya simpan token Page)." if ok
                       else "Token Page TIDAK bisa diambil — pastikan izin pages_show_list & Page dicentang."))
            if env("IG_USER_ID"):
                r = requests.get(f"https://graph.facebook.com/{v}/{env('IG_USER_ID')}",
                                 params={"fields": "username", "access_token": meta._token()}, timeout=30).json()
                say(OK if "username" in r else BAD, f"Instagram: {'@' + r['username'] if 'username' in r else r.get('error', {}).get('message')}")
        except Exception as e:
            say(BAD, f"Meta error: {e}")

    print("\n======================================================\n")
    if env("TELEGRAM_CHAT_ID") and tok:
        telegram.send("🩺 <b>Hasil cek kesehatan</b>\n" + html.escape("\n".join(out)))
