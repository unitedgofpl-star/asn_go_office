"""Kaka Natalia (meja TikTok) — membuat paket TikTok siap posting: video slideshow 9:16 + caption TikTok.

API resmi TikTok hanya mengizinkan posting PUBLIK setelah aplikasi lolos audit TikTok,
jadi paket ini dikirim ke Telegram dan diposting dari HP (simpan video → TikTok → + → unggah).
"""
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .. import telegram
from ..core import ROOT, PUBLIC

W, H = 1080, 1920
FONTS = ROOT / "assets" / "fonts"


def _font(w, s):
    return ImageFont.truetype(str(FONTS / f"Poppins-{w}.ttf"), s)


def _frame(slide_path, cfg, idx, total):
    c = cfg["brand"]["colors"]
    bg = Image.new("RGB", (W, H), c["bg"])
    d = ImageDraw.Draw(bg)
    # header & footer bermerek (area aman TikTok: atas 150px, bawah 400px tertutup UI)
    from .desain import put_logo
    put_logo(bg, W / 2, 150, 90, anchor="ma")
    d = ImageDraw.Draw(bg)
    d.text((W / 2, 268), f"{idx}/{total}", font=_font("Medium", 28), fill=c["muted"], anchor="mm")
    sl = Image.open(slide_path).convert("RGB").resize((W, 1350))
    bg.paste(sl, (0, 300))
    d.rectangle([0, 1650, W / 2, 1662], fill="#E63946")
    d.rectangle([W / 2, 1650, W, 1662], fill="#FFFFFF")
    tt = cfg.get("tiktok", {}).get("handle", "")
    if tt:
        d.text((W / 2, 1710), f"Simpan & follow {tt}", font=_font("Medium", 34), fill=c["text"], anchor="mm")
    return bg


def _ffmpeg():
    """ffmpeg bawaan paket imageio-ffmpeg (selalu ada setelah pip install); cadangan: ffmpeg sistem."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def narration(cfg, d):
    """Teks narasi per slide dari isi draft (urutan sama dengan slide)."""
    c = d.get("content", {})
    n = len(d.get("images", []))
    if c.get("narasi"):
        seg = list(c["narasi"])
    else:
        name = cfg.get("influencer", {}).get("name", "Cicilia")
        seg = [f"Halo Rekan ASN, {name} di sini! {c.get('hook', '')}. {c.get('subtitle', '')}"]
        items = c.get("items") or []
        if items:
            seg.append(f"Ada {len(items)} poin penting. " + ". ".join(i.get("title", "") for i in items))
        for it in c.get("details") or []:
            body = re.sub(r'^\s*prompt\s*:\s*', 'Contoh prompt-nya: ', str(it.get("body", "")), flags=re.I)
            words = body.split()
            seg.append(f"{it.get('title', '')}. " + " ".join(words[:45]))
        seg.append(f"{c.get('cta', 'Simpan dan bagikan ke rekan kerja')}. Jangan lupa follow A S N GO Digitals, ya!")
    seg = (seg + [""] * n)[:n]
    if n and not seg[-1]:
        seg[-1] = "Simpan dan follow A S N GO Digitals, ya!"
    return seg


def make_video(cfg, draft_id, image_paths, d=None):
    from . import suara
    out = PUBLIC / draft_id / "tiktok.mp4"
    frames = [_frame(ROOT / p, cfg, i, len(image_paths)) for i, p in enumerate(image_paths, 1)]
    narr = narration(cfg, d or {"images": image_paths, "content": {}})
    mood = ((d or {}).get("content", {}) or {}).get("mood", "tenang")
    suara.compose(cfg, frames, narr, out, seed=hash(draft_id) % 10000, mood=mood, min_dur=3.0)
    return out


def caption(cfg, content):
    seen, tags = set(), []
    for t in (content.get("hashtags") or [])[:5] + cfg.get("tiktok", {}).get("hashtags", []):
        if t.lower() not in seen:
            seen.add(t.lower())
            tags.append(t)
    tags = tags[:8]
    body = (content.get("caption") or "").split("\n\n")[0][:300]
    return f"{content.get('hook', '')} 👇\n\n{body}\n\n{' '.join(tags)}".strip()


def send_package(cfg, state, draft_id):
    d = state.d["drafts"].get(draft_id)
    if not d:
        telegram.send(f"Draft #{draft_id} tidak ditemukan.")
        return
    state.work("humas", f"Menyiapkan paket TikTok #{draft_id}...")
    try:
        video = (ROOT / d["video"]) if d.get("type") == "reels" else make_video(cfg, draft_id, d["images"], d)
        cap = caption(cfg, d["content"])
        telegram.send_video(video, f"📱 Paket TikTok #{draft_id} — simpan video ini lalu unggah di TikTok")
        import html
        telegram.send(
            "📝 <b>Caption TikTok</b> (tekan untuk menyalin):\n"
            f"<code>{html.escape(cap)}</code>\n\n"
            "Cara posting (±1 menit): simpan video ↓ → buka TikTok → <b>+</b> → Unggah → pilih video → "
            "tambahkan musik yang sedang tren → tempel caption → aktifkan label <b>Konten buatan AI</b> → Posting.")
        state.done("humas", f"Paket TikTok #{draft_id} dikirim ke Bos")
    except Exception as e:
        telegram.send(f"⚠️ Paket TikTok gagal dibuat: {html_escape(e)}")
        state.done("humas", f"Paket TikTok gagal: {e}")


def html_escape(e):
    import html
    return html.escape(str(e))
