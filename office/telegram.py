"""Telegram Bot API — saluran perintah antara Anda (Bos) dan kantor."""
import json
from contextlib import ExitStack

import requests

from .core import env

API = "https://api.telegram.org/bot{token}/{method}"


def _call(method: str, data=None, files=None, timeout=60):
    token = env("TELEGRAM_BOT_TOKEN")
    if not token:
        print(f"[telegram:dry-run] {method} {str(data)[:200]}")
        return {}
    r = requests.post(API.format(token=token, method=method), data=data, files=files, timeout=timeout)
    js = r.json()
    if not js.get("ok"):
        print(f"[telegram] {method} gagal: {js}")
    return js.get("result", {})


def owner_chat() -> str:
    return env("TELEGRAM_CHAT_ID")


def send(text: str, buttons=None, chat_id=None):
    """Kirim pesan (HTML). buttons = [[("Label", "callback_data"), ...], ...]"""
    data = {"chat_id": chat_id or owner_chat(), "text": text[:4000], "parse_mode": "HTML",
            "disable_web_page_preview": "true"}
    if buttons:
        data["reply_markup"] = json.dumps(
            {"inline_keyboard": [[{"text": t, "callback_data": c} for t, c in row] for row in buttons]})
    return _call("sendMessage", data)


def send_album(paths, caption="", chat_id=None):
    """Kirim pratinjau carousel (maks 10 gambar)."""
    paths = list(paths)[:10]
    with ExitStack() as stack:
        files, media = {}, []
        for i, p in enumerate(paths):
            files[f"p{i}"] = stack.enter_context(open(p, "rb"))
            item = {"type": "photo", "media": f"attach://p{i}"}
            if i == 0 and caption:
                item["caption"] = caption[:1000]
            media.append(item)
        return _call("sendMediaGroup", {"chat_id": chat_id or owner_chat(), "media": json.dumps(media)}, files, timeout=120)


def answer_callback(cb_id: str, text: str = "Diproses ✅"):
    return _call("answerCallbackQuery", {"callback_query_id": cb_id, "text": text})


def get_updates(offset: int):
    res = _call("getUpdates", {"offset": offset, "timeout": 0, "allowed_updates": json.dumps(["message", "callback_query"])})
    return res if isinstance(res, list) else []
