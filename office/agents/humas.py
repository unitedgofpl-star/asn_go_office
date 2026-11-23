"""Kaka Natalia — menerbitkan draft yang sudah disetujui ke Instagram & Facebook Page."""
from .. import meta, telegram
from ..core import ROOT, env, now_wit


def caption_of(d):
    c = d["content"]
    tags = " ".join(c.get("hashtags", []))
    return f"{c.get('caption', '')}\n\n{tags}".strip()


def public_urls(paths):
    """URL publik gambar dari repo GitHub publik (dibutuhkan Instagram API)."""
    repo = env("GITHUB_REPOSITORY")
    branch = env("GITHUB_REF_NAME", "main")
    base = env("PUBLIC_BASE_URL") or f"https://raw.githubusercontent.com/{repo}/{branch}"
    return [f"{base.rstrip('/')}/{p}" for p in paths]


TOKEN_ERR = ("validating access token", "session has expired", "invalid oauth", "oauthexception", "code 190",
             "error_subcode", "has not authorized application", "password has been changed", "session is invalid")


def token_bermasalah(errors):
    t = " ".join(errors).lower()
    return any(k in t for k in TOKEN_ERR)


def kirim_manual(cfg, state, draft_id, alasan_baru):
    """Token Meta mati: kirim paket siap-posting ke Telegram supaya Bos bisa posting manual dari HP."""
    import html
    d = state.d["drafts"][draft_id]
    is_reels = d.get("type") == "reels"
    if alasan_baru:
        telegram.send("🔑 <b>Akses Meta (IG & FB) terputus</b> — token tidak berlaku lagi.\n"
                      "Mulai sekarang konten tetap dibuat sesuai jadwal dan dikirim ke sini sebagai <b>paket posting manual</b>. "
                      "Notifikasi error tidak akan diulang-ulang.\n"
                      "Setelah token baru dipasang, posting otomatis jalan lagi dengan sendirinya. Cek kapan saja: /cek")
    head = f"📦 <b>Paket posting manual #{draft_id}</b> — {html.escape(d.get('content', {}).get('hook', '')[:80])}"
    if is_reels:
        telegram.send_video(ROOT / d["video"], f"🎬 Reels #{draft_id} — simpan, lalu unggah di IG Reels / FB")
    else:
        telegram.send_album([ROOT / p for p in d["images"]], f"🖼 Carousel #{draft_id} — simpan semua gambar sesuai urutan")
    cap = caption_of(d)
    telegram.send(head + "\n\n📝 <b>Caption IG/FB</b> (tekan untuk menyalin):\n<code>" + html.escape(cap[:3300]) + "</code>\n\n"
                  f"Sudah diposting? Ketik <code>/sudah {draft_id}</code> supaya tercatat di jadwal & laporan.")


def publish(cfg, state, draft_id):
    d = state.d["drafts"][draft_id]
    state.work("humas", f"Menerbitkan #{draft_id} ke IG & FB...")
    cap = caption_of(d)
    result, errors = {}, []
    from .. import gitsync
    is_reels = d.get("type") == "reels"
    media = [d["video"], d["images"][0]] if is_reels else d["images"]
    gitsync.push_media(media, public_urls(media))
    if env("IG_USER_ID"):
        try:
            if is_reels:
                v, c = public_urls([d["video"], d["images"][0]])
                result["ig"] = meta.ig_publish_reel(v, cap, c)
            else:
                result["ig"] = meta.ig_publish_carousel(public_urls(d["images"]), cap)
        except Exception as e:
            errors.append(f"IG: {e}")
    if env("FB_PAGE_ID"):
        try:
            if is_reels:
                result["fb"] = meta.fb_publish_video(str(ROOT / d["video"]), cap)
            else:
                result["fb"] = meta.fb_publish_album([str(ROOT / p) for p in d["images"]], cap)
        except Exception as e:
            errors.append(f"FB: {e}")
    d["published"] = result
    d["published_at"] = now_wit().isoformat(timespec="minutes")
    meta_state = state.d.setdefault("meta", {})
    if not result and errors and token_bermasalah(errors):
        baru = not meta_state.get("token_mati")
        meta_state["token_mati"] = now_wit().isoformat(timespec="minutes")
        d["status"] = "manual"
        d["errors"] = errors
        print("Token Meta mati:", errors)
        kirim_manual(cfg, state, draft_id, baru)
        state.done("humas", f"#{draft_id} dikirim sebagai paket manual (token Meta mati)")
        if cfg.get("tiktok", {}).get("enabled", True):
            from . import tiktok
            tiktok.send_package(cfg, state, draft_id)
        return
    if result and meta_state.pop("token_mati", None):
        telegram.send("✅ <b>Akses Meta pulih</b> — posting otomatis ke IG & FB jalan lagi.")
    if result:
        d["status"] = "published"
        state.d["stats"]["published"] += 1
    else:
        d["status"] = "failed"
    d["errors"] = errors
    msg = f"📣 <b>#{draft_id} {('terbit' if result else 'GAGAL terbit')}</b>\n"
    msg += "\n".join(f"• {k.upper()}: {v}" for k, v in result.items())
    if errors:
        msg += "\n⚠️ " + "\n⚠️ ".join(errors)
    telegram.send(msg)
    state.done("humas", f"#{draft_id} → {', '.join(result) or 'gagal'}")
    if result and cfg.get("tiktok", {}).get("enabled", True):
        from . import tiktok
        tiktok.send_package(cfg, state, draft_id)


def publish_due(cfg, state):
    """Terbitkan semua draft 'approved' yang jadwalnya sudah lewat."""
    now = now_wit().isoformat(timespec="minutes")
    for did, d in list(state.d["drafts"].items()):
        if d.get("status") == "approved" and d.get("scheduled_at", "") <= now:
            publish(cfg, state, did)
