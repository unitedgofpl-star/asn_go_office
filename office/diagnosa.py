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
    tok = env("TELEGRAM_BOT_TOKEN")
    if tok:
        me = telegram.raw("getMe")
        if me.get("ok"):
            say(OK, f"Token bot valid: @{me['result']['username']}")
        else:
            say(BAD, f"Token bot DITOLAK Telegram ({me.get('description')}). Salin ulang token dari @BotFather tanpa spasi.")

        # 3. Webhook (webhook aktif = polling tidak menerima pesan)
        wh = telegram.raw("getWebhookInfo")
        url = (wh.get("result") or {}).get("url")
        if url and env("TELEGRAM_MODE").lower() != "webhook":
            telegram.raw("deleteWebhook")
            say(WARN, f"Webhook aktif ({url}) memblokir polling → SUDAH DIHAPUS otomatis.")
        elif url:
            say(OK, f"Mode webhook (Cloudflare) aktif: {url}")
        else:
            say(OK, "Tidak ada webhook — mode polling siap.")

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
        model = env("GEMINI_MODEL", "gemini-2.5-flash")
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={env('GEMINI_API_KEY')}",
                json={"contents": [{"parts": [{"text": "Jawab: OK"}]}]}, timeout=60)
            say(OK if r.ok else BAD, f"Gemini ({model}): {'berfungsi' if r.ok else r.json().get('error', {}).get('message', r.text)[:160]}")
        except Exception as e:
            say(BAD, f"Gemini error: {e}")

    # 7. Meta
    if env("META_PAGE_TOKEN"):
        try:
            v = env("GRAPH_VERSION", "v21.0")
            r = requests.get(f"https://graph.facebook.com/{v}/me", params={"access_token": env("META_PAGE_TOKEN")}, timeout=30).json()
            say(OK if "id" in r else BAD, f"Token Meta: {'valid untuk ' + r.get('name', '') if 'id' in r else r.get('error', {}).get('message')}")
            if env("IG_USER_ID"):
                r = requests.get(f"https://graph.facebook.com/{v}/{env('IG_USER_ID')}",
                                 params={"fields": "username", "access_token": env("META_PAGE_TOKEN")}, timeout=30).json()
                say(OK if "username" in r else BAD, f"Instagram: {'@' + r['username'] if 'username' in r else r.get('error', {}).get('message')}")
        except Exception as e:
            say(BAD, f"Meta error: {e}")

    print("\n======================================================\n")
    if env("TELEGRAM_CHAT_ID") and tok:
        telegram.send("🩺 <b>Hasil cek kesehatan</b>\n" + html.escape("\n".join(out)))
