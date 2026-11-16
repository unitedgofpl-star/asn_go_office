"""Kaka Natalia (meja TikTok) — membuat paket TikTok siap posting: video slideshow 9:16 + caption TikTok.

API resmi TikTok hanya mengizinkan posting PUBLIK setelah aplikasi lolos audit TikTok,
jadi paket ini dikirim ke Telegram dan diposting dari HP (simpan video → TikTok → + → unggah).
"""
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
    d.text((W / 2, 200), cfg["brand"].get("wordmark", "ASN GO DIGITALS"), font=_font("BoldItalic", 44), fill=c["gold"], anchor="mm")
    d.text((W / 2, 255), f"{idx}/{total}", font=_font("Medium", 30), fill=c["muted"], anchor="mm")
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


def make_video(cfg, draft_id, image_paths, seconds=3.5):
    out = PUBLIC / draft_id / "tiktok.mp4"
    tmp = Path(tempfile.mkdtemp())
    lst = []
    for i, p in enumerate(image_paths, 1):
        fp = tmp / f"f{i:02d}.jpg"
        _frame(ROOT / p, cfg, i, len(image_paths)).save(fp, quality=92)
        lst.append(f"file '{fp}'\nduration {seconds}")
    lst.append(f"file '{tmp / f'f{len(image_paths):02d}.jpg'}'")  # syarat concat: frame terakhir diulang
    (tmp / "list.txt").write_text("\n".join(lst))
    cmd = [_ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
           "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
           "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
           "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
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
        video = (ROOT / d["video"]) if d.get("type") == "reels" else make_video(cfg, draft_id, d["images"])
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
