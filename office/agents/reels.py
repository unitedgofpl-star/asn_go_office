"""Kaka Elisa — video Reels 9:16 (±25 detik) dari naskah AI.

Alur: naskah (hook → 5–6 poin → ajakan) → frame bertema (memakai tema & pose acak dari desain.py)
→ animasi zoom lembut + transisi bervariasi (ffmpeg) → musik latar bila ada di assets/music/*.mp3 → MP4.
Gratis: Pillow + ffmpeg bawaan imageio-ffmpeg.
"""
import random
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from .. import llm
from ..core import ROOT, PUBLIC
from . import desain as D
from .tiktok import _ffmpeg

W, H = 1080, 1920
MUSIC = ROOT / "assets" / "music"
TRANSITIONS = ["fade", "slideleft", "smoothup", "circleopen", "wipeleft", "slideup", "radial", "smoothleft"]

SCHEMA = """Balas HANYA JSON:
{
 "hook": "kalimat pembuka 4-8 kata yang menghentikan scroll (pertanyaan/klaim berani)",
 "mood": "suasana Cicilia yang paling cocok dengan isi: ceria | semangat | terkejut | cemberut | tegas | sedih | sayang | tenang | menjelaskan",
 "beats": [{"text": "satu poin, maks 14 kata, bahasa lisan", "icon": "1 emoji"}],
 "cta": "ajakan penutup maks 10 kata",
 "caption": "caption Reels 40-90 kata, orang pertama sebagai Cicilia, ajakan simpan/bagikan, pertanyaan komentar",
 "hashtags": ["#..."]
}
beats berisi 5-6 poin, runtut, padat, langsung praktik."""


def write_script(cfg, state, pillar, topic, news=None, product=None, avoid=None):
    from .naskah import _system
    state.work("naskah", f"Menulis naskah Reels: {topic[:45]}")
    prompt = f"Pilar: {pillar['name']}\nTopik: {topic}\nBuat naskah VIDEO REELS pendek (±25 detik) yang terasa cepat dan bertenaga.\n"
    if news:
        prompt += "Berita tren minggu ini (inspirasi saja):\n" + "\n".join(news) + "\n"
    if product:
        prompt += f"Boleh sebut di akhir: {product['name']} ({product['price']}) — link di bio.\n"
    if avoid:
        prompt += "Jangan mengulang judul/topik ini: " + "; ".join(avoid[-12:]) + "\n"
    prompt += SCHEMA
    sc = llm.ask(prompt, _system(cfg), as_json=True)
    state.done("naskah", f"Naskah Reels: \"{sc.get('hook', '')}\"")
    return sc


# ------------------------------------------------------------------ frame 9:16
def _bg(t):
    img = D.background(t)  # 1080x1350
    full = Image.new("RGBA", (W, H), D.hexc(t["bg"]))
    full.alpha_composite(img.resize((W, H)))
    return full


def _brand(img, t, cfg):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([60, 150, 116, 206], 14, fill=D.hexc(t["accent"]))
    d.text((88, 178), "AG", font=D.F("pop_b", 24), fill="white", anchor="mm")
    d.text((132, 158), cfg["brand"]["name"], font=D.F("pop_b", 28), fill=D.hexc(t["text"]))
    d.text((132, 190), cfg["brand"]["handle"], font=D.F("pop_r", 22), fill=D.hexc(t["muted"]))


def frame_hook(cfg, t, st, sc):
    img = _bg(t)
    person, stem = D.load_pose(st["pose"], st["flip"])
    if person is not None:
        D.place_person(img, person, 1100 if stem != "presentasi" else 900, W / 2 + (60 if stem == "presentasi" else 0), H - 330, t["glow"])
    d = ImageDraw.Draw(img)
    # pita judul di atas (zona aman TikTok/IG: hindari 250px atas & 400px bawah)
    f, ls, s = D.fit(d, sc["hook"].upper(), t["title"], 100, W - 140, 460, min_size=56, spacing=1.06, max_lines=4)
    y = 290
    for ln in ls:
        tw = d.textlength(ln, font=f)
        d.rounded_rectangle([W / 2 - tw / 2 - 24, y - 8, W / 2 + tw / 2 + 24, y + s * 1.02], 14, fill=D.hexc(t["accent"]))
        d.text((W / 2, y), ln, font=f, fill="white", anchor="ma")
        y += s * 1.12
    d.text((W / 2, H - 300), f"bareng {cfg.get('influencer', {}).get('name', 'Cicilia')}", font=D.F("pop_i", 26),
           fill=D.hexc(t["muted"]), anchor="mm")
    _brand(img, t, cfg)
    return img


def frame_beat(cfg, t, st, beat, n, total, variant):
    img = _bg(t)
    d = ImageDraw.Draw(img)
    _brand(img, t, cfg)
    text = beat.get("text", "")
    if variant == 0:  # kartu tengah
        f, ls, s = D.fit(d, text, t["title"], 78, W - 220, 700, min_size=44, spacing=1.15)
        bh = int(len(ls) * s * 1.15 + 120)
        y0 = int(H / 2 - bh / 2)
        d.rounded_rectangle([70, y0, W - 70, y0 + bh], 44, fill=D.hexc(t["card"]))
        D.lines_at(d, (120, y0 + 60), ls, f, s, D.hexc(t["card_text"]), 1.15)
        d.ellipse([70, y0 - 90, 210, y0 + 50], fill=D.hexc(t["accent"]))
        d.text((140, y0 - 20), str(n), font=D.F("int_k", 80), fill="white", anchor="mm")
        D.icon_circle(img, t, W - 150, y0 - 20, 66, beat.get("icon"))
    elif variant == 1:  # angka raksasa + teks besar
        d.text((40, 300), f"{n:02d}", font=D.F("int_k", 420), fill=D.hexc(t["gold"], 70))
        f, ls, s = D.fit(d, text, t["title"], 86, W - 140, 760, min_size=46, spacing=1.12)
        y = D.lines_at(d, (70, 800), ls, f, s, D.hexc(t["text"]), 1.12)
        d.rectangle([70, y + 20, 260, y + 34], fill=D.hexc(t["accent"]))
        D.icon_circle(img, t, W - 170, 480, 90, beat.get("icon"))
    else:  # Cicilia bicara (gelembung)
        D.portrait(img, t, D.face_crop(st["pose"], st["flip"], st.get("expr")), 170, 520, 100)
        d.text((300, 480), cfg.get("influencer", {}).get("name", "Cicilia"), font=D.F("pop_b", 40), fill=D.hexc(t["text"]))
        d.text((300, 532), f"Poin {n} dari {total}", font=D.F("pop_r", 28), fill=D.hexc(t["muted"]))
        f, ls, s = D.fit(d, text, "pop_b", 70, W - 260, 760, min_size=40, spacing=1.2)
        bh = int(len(ls) * s * 1.2 + 110)
        y0 = 690
        d.rounded_rectangle([70, y0, W - 70, y0 + bh], 44, fill=D.hexc(t["accent"]))
        d.polygon([(130, y0 + 2), (190, y0 + 2), (150, y0 - 50)], fill=D.hexc(t["accent"]))
        D.lines_at(d, (120, y0 + 55), ls, f, s, (255, 255, 255, 255), 1.2)
    # progres
    x0 = (W - total * 30) / 2
    for i in range(total):
        d.rounded_rectangle([x0 + i * 30, H - 430, x0 + i * 30 + 22, H - 422], 4,
                            fill=D.hexc(t["gold"]) if i < n else D.hexc(t["muted"], 90))
    return img


def frame_cta(cfg, t, st, sc, product):
    img = _bg(t)
    d = ImageDraw.Draw(img)
    _brand(img, t, cfg)
    D.portrait(img, t, D.face_crop(st["pose"], not st["flip"], st.get("expr")), W // 2, 520, 170)
    f, ls, s = D.fit(d, sc.get("cta", "Simpan & follow untuk tips berikutnya!"), t["title"], 72, W - 160, 300, min_size=42, spacing=1.12)
    y = 760
    for ln in ls:
        d.text((W / 2, y), ln, font=f, fill=D.hexc(t["text"]), anchor="ma")
        y += s * 1.12
    d.rounded_rectangle([W / 2 - 300, y + 30, W / 2 + 300, y + 130], 50, fill=D.hexc(t["accent"]))
    d.text((W / 2, y + 80), f"Follow {cfg['brand']['handle']}", font=D.F("pop_b", 38), fill="white", anchor="mm")
    if product:
        y += 180
        d.rounded_rectangle([110, y, W - 110, y + 200], 32, fill=D.hexc("#FFFFFF", 245))
        d.text((W / 2, y + 60), product["name"], font=D.F("pop_b", 40), fill=D.hexc("#0B1F3A"), anchor="mm")
        d.text((W / 2, y + 130), f"{product['price'].split(' (')[0]} • link di bio", font=D.F("pop_m", 34),
               fill=D.hexc(t["accent"]), anchor="mm")
    return img


# ------------------------------------------------------------------ video
def render(cfg, state, draft_id, sc, pillar_name, pillar_id, product=None):
    st = D.choose_style(state, draft_id, pillar_id, "reels", {"hook": sc.get("hook", ""), "mood": sc.get("mood")})
    t = D.THEMES[st["theme"]]
    state.work("desain", f"Membuat Reels gaya {st['theme']}...")
    rnd = random.Random(draft_id)
    beats = (sc.get("beats") or [])[:6]
    frames = [frame_hook(cfg, t, st, sc)]
    start = rnd.randrange(3)
    for i, b in enumerate(beats, 1):
        frames.append(frame_beat(cfg, t, st, b, i, len(beats), (start + i) % 3))
    frames.append(frame_cta(cfg, t, st, sc, product))
    out_dir = PUBLIC / draft_id
    out_dir.mkdir(parents=True, exist_ok=True)
    cover = out_dir / "cover.jpg"
    frames[0].convert("RGB").save(cover, quality=90)
    name = cfg.get("influencer", {}).get("name", "Cicilia")
    narr = [f"Halo Rekan ASN, {name} di sini! {sc.get('hook', '')}"] + [b_.get("text", "") for b_ in beats] + \
           [f"{sc.get('cta', '')} Follow A S N GO Digitals, ya!"]
    from . import suara
    state.work("desain", "Merekam suara Cicilia & meracik musik latar...")
    out, total = suara.compose(cfg, frames, narr, out_dir / "reels.mp4", seed=hash(draft_id) % 10000, mood=st.get("mood", "tenang"))
    state.done("desain", f"Reels {total:.0f} detik siap (gaya {st['theme']})")
    return str(out.relative_to(ROOT)), str(cover.relative_to(ROOT))
