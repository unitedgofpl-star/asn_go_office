"""Kaka Elisa — carousel 1080x1350 dengan GAYA BERVARIASI.

Setiap konten mendapat kombinasi berbeda (dipilih sesuai pilar, format, dan isi, dan tidak mengulang gaya konten sebelumnya):
  • 6 tema warna   : navy · merah (editorial krem) · tosca · ungu (AI) · berita (merah dramatis/abu) · kertas (Lora, krem)
  • 5 cover        : kanan · kiri · berita · angka · potret
  • 4 slide daftar : kartu · timeline · grid · ceklis
  • 4 slide isi    : kartu · chat (Cicilia bicara) · versus (mitos/fakta) · angka
  • Cicilia        : 3 pose × cermin kiri/kanan × badan/potret wajah × posisi berbeda
Gratis: Pillow + pose di assets/influencer/. Opsional: foto cover baru dari Gemini Image (agents/foto.py).
"""
import math
import random
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageChops

from ..core import ROOT, PUBLIC

W, H = 1080, 1350
FONTS = ROOT / "assets" / "fonts"
POSES = ROOT / "assets" / "influencer" / "pose"          # nama file: <suasana>__<nama>.png (latar transparan)
EXPR = ROOT / "assets" / "influencer" / "ekspresi"       # wajah/setengah badan: <ekspresi>.png
HALF_BODY = {"tenang__melipat_tangan", "menjelaskan__presentasi", "semangat__tangan_mengepal"}
# suasana konten → ekspresi wajah yang cocok
MOOD_EXPR = {"ceria": ["ceria", "senang", "gembira", "tertawa"], "semangat": ["semangat", "gembira"], "terkejut": ["terkejut"],
             "cemberut": ["cemberut", "kecewa"], "tegas": ["cemberut"], "sedih": ["sedih", "kecewa"],
             "sayang": ["senang", "ceria"], "tenang": ["ceria", "senang"], "menjelaskan": ["senang", "ceria"]}
MOOD_FALLBACK = {"sedih": "tenang", "cemberut": "tegas", "tegas": "cemberut"}
FMT_MOOD = {"carousel_mitos": "terkejut", "carousel_promo": "sayang", "carousel_tutorial": "menjelaskan",
            "carousel_listicle": "ceria", "carousel_prompt": "semangat"}
MOODS = sorted(MOOD_EXPR)
EMOJI_PATHS = ["/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", str(FONTS / "NotoColorEmoji.ttf")]

# ------------------------------------------------------------------ font
FONT_FILES = {
    "pop_b": "Poppins-Bold.ttf", "pop_m": "Poppins-Medium.ttf", "pop_r": "Poppins-Regular.ttf",
    "pop_i": "Poppins-Italic.ttf", "pop_bi": "Poppins-BoldItalic.ttf", "pop_mi": "Poppins-MediumItalic.ttf",
    "int_k": "InterDisplay-Black.otf", "int_xb": "InterDisplay-ExtraBold.otf", "int_sb": "InterDisplay-SemiBold.otf",
    "lora": "Lora-Variable.ttf", "mono": "DejaVuSansMono.ttf", "mono_b": "DejaVuSansMono-Bold.ttf",
}
_FC = {}


def F(key, size):
    k = (key, int(size))
    if k not in _FC:
        f = ImageFont.truetype(str(FONTS / FONT_FILES.get(key, "Poppins-Regular.ttf")), int(size))
        if key == "lora":
            try:
                f.set_variation_by_name("Bold")
            except Exception:
                pass
        _FC[k] = f
    return _FC[k]


def sub_col(t):
    """Warna teks kecil di atas kartu: abu gelap bila kartu terang."""
    r, g, b, _ = hexc(t["card"])
    return hexc("#5E6673") if (r * .299 + g * .587 + b * .114) > 150 else hexc(t["muted"])


def hexc(h, a=255):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


# ------------------------------------------------------------------ tema
THEMES = {
    "navy":   dict(dark=True, bg="#0B1F3A", bg2="#12305A", card="#163A6B", card_text="#FFFFFF", text="#FFFFFF", muted="#B8C4D6",
                   accent="#E63946", gold="#F4B942", pattern="kawung", title="pop_b", glow=(244, 185, 66)),
    "merah":  dict(dark=False, bg="#FFF6E9", bg2="#FBE3CF", card="#FFFFFF", card_text="#1B1B1F", text="#1B1B1F", muted="#6B6B73",
                   accent="#C8102E", gold="#C8102E", pattern="dots", title="int_k", glow=(200, 16, 46)),
    "tosca":  dict(dark=True, bg="#053B3F", bg2="#0A5C61", card="#0E6E73", card_text="#FFFFFF", text="#FFFFFF", muted="#BFE3E0",
                   accent="#FF8A3D", gold="#FFD166", pattern="stripes", title="pop_b", glow=(255, 209, 102)),
    "ungu":   dict(dark=True, bg="#160F36", bg2="#36206F", card="#2E1E66", card_text="#FFFFFF", text="#FFFFFF", muted="#CFC4F5",
                   accent="#FF4D8D", gold="#7CF3FF", pattern="grid", title="int_k", glow=(124, 243, 255)),
    "berita": dict(dark=True, bg="#5E5B57", bg2="#4A4744", card="#EAE9E7", card_text="#161618", text="#FFFFFF", muted="#E2DFDA",
                   accent="#B22228", gold="#F4B942", pattern="noise", title="int_k", glow=(255, 70, 40)),
    "kertas": dict(dark=False, bg="#F4EFE6", bg2="#ECE3D2", card="#FFFFFF", card_text="#20242B", text="#20242B", muted="#5E6673",
                   accent="#2563EB", gold="#E08A00", pattern="paper", title="lora", glow=(37, 99, 235)),
}
PILLAR_THEMES = {"ai": ["ungu", "navy", "kertas", "berita"], "desa": ["tosca", "merah", "kertas", "navy"],
                 "asn": ["navy", "merah", "berita", "tosca"], "promo": ["merah", "navy", "berita", "ungu"]}
FMT_LIST = {"carousel_tutorial": ["timeline", "kartu"], "carousel_listicle": ["grid", "kartu", "ceklis"],
            "carousel_prompt": ["kartu", "grid"], "carousel_mitos": ["ceklis", "kartu"], "carousel_promo": ["grid", "kartu"]}
FMT_DETAIL = {"carousel_tutorial": ["kartu", "angka"], "carousel_listicle": ["kartu", "chat", "angka"],
              "carousel_prompt": ["chat"], "carousel_mitos": ["versus"], "carousel_promo": ["chat", "kartu"]}


def choose_style(state, draft_id, pillar_id, fmt, content):
    """Pilih kombinasi gaya yang cocok dengan isi dan berbeda dari konten sebelumnya."""
    rnd = random.Random(f"{draft_id}-{content.get('hook', '')}")
    hist = state.d.setdefault("style_hist", [])
    last = hist[-1] if hist else {}

    def pick(options, key):
        opts = [o for o in options if o != last.get(key)] or options
        return rnd.choice(opts)
    key = "promo" if fmt == "carousel_promo" else pillar_id
    theme = pick(PILLAR_THEMES.get(key, list(THEMES)), "theme")
    covers = ["kanan", "kiri", "potret"]
    if THEMES[theme]["dark"]:
        covers.append("berita")
    if re.search(r"\d+", content.get("hook", "")):
        covers += ["angka", "angka"]
    mood = content.get("mood") if content.get("mood") in MOOD_EXPR else FMT_MOOD.get(fmt, "ceria")
    poses = [p.stem for p in POSES.glob("*.png")] or ["tenang__melipat_tangan"]
    m = mood
    match = [p for p in poses if p.startswith(m + "__")]
    while not match and m in MOOD_FALLBACK:
        m = MOOD_FALLBACK[m]
        match = [p for p in poses if p.startswith(m + "__")]
    match = match or poses
    exprs = [e for e in MOOD_EXPR.get(mood, ["ceria"]) if (EXPR / f"{e}.png").exists()]
    style = {
        "mood": mood, "expr": rnd.choice(exprs) if exprs else None,
        "theme": theme, "cover": pick(covers, "cover"),
        "list": pick(FMT_LIST.get(fmt, ["kartu"]), "list"), "detail": pick(FMT_DETAIL.get(fmt, ["kartu"]), "detail"),
        "pose": pick(match, "pose"),
        "flip": rnd.random() < .5, "cta": rnd.choice(["badan", "potret"]),
    }
    hist.append(style)
    state.d["style_hist"] = hist[-20:]
    return style


# ------------------------------------------------------------------ util teks
def wrap(draw, text, font, width):
    lines = []
    for para in str(text).split("\n"):
        cur = ""
        for w in para.split():
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=font) <= width:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def fit(draw, text, key, size, width, max_h, min_size=22, spacing=1.25, max_lines=99):
    while size >= min_size:
        f = F(key, size)
        lines = wrap(draw, text, f, width)
        if len(lines) * size * spacing <= max_h and len(lines) <= max_lines:
            return f, lines, size
        size -= 2
    f = F(key, min_size)
    return f, wrap(draw, text, f, width)[:max_lines], min_size


def lines_at(draw, xy, lines, font, size, fill, spacing=1.25, anchor=None):
    x, y = xy
    for ln in lines:
        draw.text((x, y), ln, font=font, fill=fill, anchor=anchor)
        y += size * spacing
    return y


# ------------------------------------------------------------------ latar
def background(t, seed=0):
    img = Image.new("RGBA", (W, H), hexc(t["bg"]))
    g = Image.new("RGBA", (W, H))
    gd = ImageDraw.Draw(g)
    b1, b2 = hexc(t["bg"]), hexc(t["bg2"])
    for y in range(0, H, 2):
        k = y / H
        gd.rectangle([0, y, W, y + 2], fill=tuple(int(b1[i] + (b2[i] - b1[i]) * k) for i in range(3)) + (255,))
    img = Image.alpha_composite(img, g)
    pat = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    p = ImageDraw.Draw(pat)
    ink = hexc(t["gold"], 26 if t["dark"] else 30)
    kind = t["pattern"]
    if kind == "kawung":
        s = 90
        for gx in range(0, W + s, s):
            for gy in range(0, H + s, s):
                if math.hypot(gx - W, gy) < 520 or math.hypot(gx, gy - H) < 420:
                    r = s * .42
                    for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                        ex, ey = gx + dx * r * .55, gy + dy * r * .55
                        rx, ry = (r * .5, r * .28) if dx else (r * .28, r * .5)
                        p.ellipse([ex - rx, ey - ry, ex + rx, ey + ry], outline=ink, width=3)
    elif kind == "dots":
        for gx in range(20, W, 36):
            for gy in range(20, H, 36):
                if gx > W * .55 and gy < H * .45:
                    p.ellipse([gx - 3, gy - 3, gx + 3, gy + 3], fill=ink)
    elif kind == "stripes":
        for k in range(-H, W, 46):
            p.line([(k, H), (k + 500, H - 500)], fill=ink, width=10)
    elif kind == "grid":
        for gx in range(0, W, 60):
            p.line([(gx, 0), (gx, H)], fill=hexc(t["gold"], 14), width=1)
        for gy in range(0, H, 60):
            p.line([(0, gy), (W, gy)], fill=hexc(t["gold"], 14), width=1)
    elif kind == "paper":
        for gy in range(150, H, 54):
            p.line([(60, gy), (W - 60, gy)], fill=hexc("#9AA4B2", 34), width=1)
        p.line([(120, 0), (120, H)], fill=hexc("#E05A5A", 50), width=2)
    img = Image.alpha_composite(img, pat)
    if kind == "noise":
        n = Image.effect_noise((W, H), 40).convert("L")
        img = Image.alpha_composite(img, Image.merge("RGBA", (n, n, n, Image.new("L", (W, H), 20))))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([-300, -300, 600, 500], fill=hexc(t["accent"], 40 if t["dark"] else 22))
    return Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(160)))


def dramatic_bg(seed=0):
    rnd = random.Random(seed)
    img = Image.new("RGBA", (W, H), (26, 4, 6, 255))
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse([W / 2 - 560, 120, W / 2 + 560, 1080], fill=(196, 40, 30, 255))
    img = Image.alpha_composite(img, g.filter(ImageFilter.GaussianBlur(170)))
    rays = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rays)
    cx, cy = W / 2, 700
    for _ in range(140):
        a, w = rnd.uniform(0, 6.283), rnd.uniform(.004, .014)
        rd.polygon([(cx + math.cos(a) * 380, cy + math.sin(a) * 380), (cx + math.cos(a - w) * 1500, cy + math.sin(a - w) * 1500),
                    (cx + math.cos(a + w) * 1500, cy + math.sin(a + w) * 1500)],
                   fill=(255, 90, 60, rnd.randint(25, 70)) if rnd.random() < .5 else (0, 0, 0, rnd.randint(60, 120)))
    img = Image.alpha_composite(img, rays)
    v = Image.new("L", (W, H), 0)
    ImageDraw.Draw(v).ellipse([-250, -150, W + 250, H + 100], fill=255)
    return Image.composite(img, Image.new("RGBA", (W, H), (8, 0, 0, 255)), v.filter(ImageFilter.GaussianBlur(160)))


# ------------------------------------------------------------------ elemen
def chrome(img, t, brand, pillar, idx, total):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([60, 56, 116, 112], 14, fill=hexc(t["accent"]))
    d.text((88, 84), "AG", font=F("pop_b", 24), fill="white", anchor="mm")
    d.text((132, 62), brand["name"], font=F("pop_b", 28), fill=hexc(t["text"]))
    d.text((132, 94), brand["handle"], font=F("pop_r", 22), fill=hexc(t["muted"]))
    tag = pillar.upper()
    tf = F("pop_m", 22)
    tw = d.textlength(tag, font=tf)
    d.rounded_rectangle([W - 100 - tw, 64, W - 60, 106], 21, fill=hexc(t["bg"], 170), outline=hexc(t["gold"]), width=2)
    d.text((W - 80 - tw / 2, 85), tag, font=tf, fill=hexc(t["gold"]), anchor="mm")
    x0 = (W - total * 22) / 2
    for i in range(total):
        r = 7 if i == idx else 5
        cx = x0 + i * 22 + 11
        d.ellipse([cx - r, H - 92 - r, cx + r, H - 92 + r], fill=hexc(t["gold"]) if i == idx else hexc(t["muted"], 90))
    d.rectangle([0, H - 26, W / 2, H], fill=hexc("#E63946"))
    d.rectangle([W / 2, H - 26, W, H], fill=hexc("#FFFFFF" if t["dark"] else "#E9E4DA"))
    if idx < total - 1:
        d.text((W - 90, H - 92), "geser", font=F("pop_m", 24), fill=hexc(t["muted"]), anchor="rm")
        d.polygon([(W - 80, H - 102), (W - 60, H - 92), (W - 80, H - 82)], fill=hexc(t["gold"]))


def emoji_tile(ch, size):
    for p in EMOJI_PATHS:
        if Path(p).exists():
            try:
                f = ImageFont.truetype(p, 109)
                tile = Image.new("RGBA", (136, 128), (0, 0, 0, 0))
                ImageDraw.Draw(tile).text((68, 64), ch, font=f, embedded_color=True, anchor="mm")
                tile = tile.crop(tile.getbbox() or (0, 0, 136, 128))
                tile.thumbnail((size, size), Image.LANCZOS)
                return tile
            except Exception:
                pass
    return None


def icon_circle(img, t, cx, cy, r, icon, ring=True):
    d = ImageDraw.Draw(img)
    if ring:
        d.ellipse([cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4], fill=hexc(t["gold"]))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=hexc("#FFF6E6"))
    tile = emoji_tile(icon, int(r * 1.1)) if icon else None
    if tile:
        img.alpha_composite(tile, (int(cx - tile.width / 2), int(cy - tile.height / 2)))
    elif icon:
        d.text((cx, cy), str(icon)[:2], font=F("pop_b", int(r * .8)), fill=hexc("#0B1F3A"), anchor="mm")


def load_pose(name, flip=False):
    f = POSES / f"{name}.png"
    if not f.exists():
        f = next(iter(sorted(POSES.glob("*.png"))), None)
    if f is None:
        return None, None
    p = Image.open(f).convert("RGBA")
    if f.stem not in HALF_BODY:  # pose seluruh badan → ambil sampai paha agar wajah besar
        p = p.crop((0, 0, p.width, int(p.height * .6)))
        p = p.crop(p.getbbox())
    if flip:
        p = ImageOps.mirror(p)
    return p, ("presentasi" if "presentasi" in f.stem else f.stem)


def face_crop(name, flip=False, expr=None):
    """Potret wajah: utamakan foto ekspresi (assets/influencer/ekspresi), cadangan potong dari pose."""
    if expr and (EXPR / f"{expr}.png").exists():
        p = Image.open(EXPR / f"{expr}.png").convert("RGBA")
        s = p.width
        p = p.crop((0, 0, s, s))
    else:
        f = POSES / f"{name}.png"
        if not f.exists():
            return None
        p = Image.open(f).convert("RGBA")
        if name in HALF_BODY:
            box = (.2, 0, .8, .4)
        else:
            box = (.28, 0, .72, .2)
        p = p.crop((int(p.width * box[0]), int(p.height * box[1]), int(p.width * box[2]), int(p.height * box[3])))
        s = min(p.size)
        p = p.crop(((p.width - s) // 2, 0, (p.width - s) // 2 + s, s))
    return ImageOps.mirror(p) if flip else p


def place_person(img, person, height, cx, bottom, glow):
    p = person.copy()
    s = height / p.height
    p = p.resize((int(p.width * s), int(p.height * s)), Image.LANCZOS)
    x, y = int(cx - p.width / 2), int(bottom - p.height)
    halo = Image.new("RGBA", p.size, tuple(glow) + (0,))
    halo.putalpha(p.split()[3].filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(v * .55)))
    img.alpha_composite(halo, (x, y))
    img.alpha_composite(p, (x, y))


def portrait(img, t, face, cx, cy, r):
    if face is None:
        return
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10], fill=hexc(t["accent"]))
    d.ellipse([cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4], fill=hexc(t["gold"]))
    bgc = Image.new("RGBA", (2 * r, 2 * r), hexc(t["bg2"]))
    fc = face.resize((2 * r, 2 * r), Image.LANCZOS)
    bgc.alpha_composite(fc)
    mask = Image.new("L", (2 * r, 2 * r), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, 2 * r, 2 * r], fill=255)
    img.paste(bgc, (cx - r, cy - r), mask)


def drip_box(img, x0, y0, x1, y1, color=(122, 14, 22)):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0, y0, x1, y1], 34, fill=color + (255,), outline=(160, 30, 36), width=3)
    rnd = random.Random(7)
    x = x0 + 30
    while x < x1 - 50:
        w, h = rnd.randint(26, 60), rnd.randint(14, 46)
        d.rounded_rectangle([x, y1 - 20, x + w, y1 + h], w // 2, fill=color + (255,))
        x += w + rnd.randint(8, 40)


def pill_simpan(img, t, x, y, name):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x, y, x + 330, y + 76], 38, fill=hexc(t["accent"]))
    d.text((x + 165, y + 38), "SIMPAN DULU", font=F("pop_b", 30), fill="white", anchor="mm")
    if name:
        d.text((x + 2, y + 96), f"bareng {name} • ilustrasi AI", font=F("pop_i", 22), fill=hexc(t["muted"]))


# ------------------------------------------------------------------ cover
def cover(cfg, t, st, content, pillar, total, scene=None):
    brand = cfg["brand"]
    name = cfg.get("influencer", {}).get("name")
    hook = content["hook"]
    kind = st["cover"]
    img = dramatic_bg(hash(hook) % 1000) if kind == "berita" else background(t)
    d = ImageDraw.Draw(img)
    tf = t["title"]

    if scene is not None:  # foto AI (mode Gemini) menempati 2/3 bawah
        s = max(W / scene.width, 900 / scene.height)
        sc = scene.convert("RGBA").resize((int(scene.width * s), int(scene.height * s)), Image.LANCZOS)
        sc = sc.crop(((sc.width - W) // 2, sc.height - 900, (sc.width - W) // 2 + W, sc.height))
        mask = Image.new("L", (W, 900), 255)
        md = ImageDraw.Draw(mask)
        for y in range(260):
            md.line([(0, y), (W, y)], fill=int(255 * y / 260))
        img.paste(sc, (0, H - 900), mask)
        kind = "kanan_foto"

    if kind in ("kanan", "kanan_foto"):
        if kind == "kanan":
            person, stem = load_pose(st["pose"], st["flip"])
            if person is not None:
                place_person(img, person, 640 if stem == "presentasi" else 760, 770, H - 26, t["glow"])
        f, ls, s = fit(d, hook.upper(), tf, 96, W - 140, 400, min_size=54, spacing=1.08, max_lines=4)
        y = lines_at(d, (70, 170), ls, f, s, hexc(t["text"]), 1.08)
        d.rounded_rectangle([70, y + 14, 250, y + 26], 6, fill=hexc(t["gold"]))
        if content.get("subtitle"):
            sf, sl, ss = fit(d, content["subtitle"], "pop_r", 36, 520, 140)
            lines_at(d, (70, y + 50), sl, sf, ss, hexc(t["muted"]))
        pill_simpan(img, t, 70, H - 300, name)

    elif kind == "kiri":
        person, stem = load_pose(st["pose"], not st["flip"])
        if person is not None:
            place_person(img, person, 700 if stem == "presentasi" else 860, 300, H - 26, t["glow"])
        f, ls, s = fit(d, hook, tf, 84, 500, 560, min_size=46, spacing=1.1, max_lines=6)
        h = len(ls) * s * 1.1
        y = lines_at(d, (520, 330 - 0 * h), ls, f, s, hexc(t["text"]), 1.1)
        d.rounded_rectangle([520, y + 14, 660, y + 26], 6, fill=hexc(t["accent"]))
        if content.get("subtitle"):
            sf, sl, ss = fit(d, content["subtitle"], "pop_r", 32, 500, 160)
            y = lines_at(d, (520, y + 50), sl, sf, ss, hexc(t["muted"]))
        pill_simpan(img, t, 520, min(y + 40, H - 300), name)

    elif kind == "berita":
        person, stem = load_pose(st["pose"], st["flip"])
        if person is not None:
            place_person(img, person, 1000, W / 2 + (90 if stem == "presentasi" else 0), 1010, (255, 70, 40))
        d.text((100, 885), "Foto: Ilustrasi AI/ASN GO", font=F("pop_bi", 20), fill=(255, 255, 255, 220))
        x0, y0, x1, y1 = 58, 925, W - 58, 1240
        drip_box(img, x0, y0, x1, y1)
        f, ls, s = fit(d, hook, "int_k", 88, x1 - x0 - 90, y1 - y0 - 70, min_size=50, spacing=1.1, max_lines=3)
        y = (y0 + y1) / 2 - len(ls) * s * 1.1 / 2
        for ln in ls:
            d.text((W / 2 + 3, y + 4), ln, font=f, fill=(60, 0, 4), anchor="ma")
            d.text((W / 2, y), ln, font=f, fill="white", anchor="ma")
            y += s * 1.1

    elif kind == "angka":
        num = re.search(r"\d+", hook).group(0)
        rest = re.sub(r"^\s*\d+\s*", "", hook, count=1) if hook.strip().startswith(num) else hook
        nf = F("int_k", 520 if len(num) == 1 else 400)
        d.text((60, 120), num, font=nf, fill=hexc(t["accent"]))
        nw = d.textlength(num, font=nf)
        f, ls, s = fit(d, rest, tf, 80, W - 140, 420, min_size=46, spacing=1.08, max_lines=5)
        y = lines_at(d, (70, 720), ls, f, s, hexc(t["text"]), 1.08)
        if content.get("subtitle"):
            sf, sl, ss = fit(d, content["subtitle"], "pop_r", 32, 640, 120)
            lines_at(d, (70, y + 24), sl, sf, ss, hexc(t["muted"]))
        portrait(img, t, face_crop(st["pose"], st["flip"], st.get("expr")), W - 200, 330 if nw < 600 else 1130, 120)
        if name:
            d.text((W - 200, 470 if nw < 600 else 990), f"{name} • AI", font=F("pop_i", 22), fill=hexc(t["muted"]), anchor="mm")

    else:  # potret
        portrait(img, t, face_crop(st["pose"], st["flip"], st.get("expr")), W // 2, 380, 190)
        f, ls, s = fit(d, hook, tf, 84, W - 160, 420, min_size=46, spacing=1.1, max_lines=4)
        y = 640
        for ln in ls:
            d.text((W / 2, y), ln, font=f, fill=hexc(t["text"]), anchor="ma")
            y += s * 1.1
        if content.get("subtitle"):
            sf, sl, ss = fit(d, content["subtitle"], "pop_r", 32, W - 220, 110)
            for ln in sl:
                d.text((W / 2, y + 20), ln, font=sf, fill=hexc(t["muted"]), anchor="ma")
                y += ss * 1.25
        d.rounded_rectangle([W / 2 - 165, H - 250, W / 2 + 165, H - 174], 38, fill=hexc(t["accent"]))
        d.text((W / 2, H - 212), "SIMPAN DULU", font=F("pop_b", 30), fill="white", anchor="mm")
        if name:
            d.text((W / 2, 600), f"bareng {name} • ilustrasi AI", font=F("pop_i", 22), fill=hexc(t["muted"]), anchor="mm")

    chrome(img, t if kind != "berita" else THEMES["navy"], brand, pillar, 0, total)
    return img


# ------------------------------------------------------------------ daftar
def list_slide(cfg, t, st, items, note, pillar, idx, total):
    img = background(t)
    chrome(img, t, cfg["brand"], pillar, idx, total)
    d = ImageDraw.Draw(img)
    n = max(len(items), 1)
    top, bot = 150, H - (190 if note else 130)
    lay = st["list"]
    ct = hexc(t["card_text"])

    if lay == "grid" and n >= 4:
        cols, rows = 2, math.ceil(n / 2)
        gw, gh = (W - 140 - 30) / 2, (bot - top - 30 * (rows - 1)) / rows
        for i, it in enumerate(items):
            r, c = divmod(i, 2)
            x0, y0 = 70 + c * (gw + 30), top + r * (gh + 30)
            d.rounded_rectangle([x0, y0, x0 + gw, y0 + gh], 28, fill=hexc(t["card"]))
            icon_circle(img, t, int(x0 + 70), int(y0 + 72), 40, it.get("icon"))
            d.text((x0 + gw - 30, y0 + 40), f"{i + 1:02d}", font=F("int_k", 44), fill=hexc(t["accent"]), anchor="ra")
            tf_, tl, ts = fit(d, it.get("title", ""), "pop_b", 36, gw - 60, gh * .32, min_size=24, spacing=1.1, max_lines=2)
            yy = lines_at(d, (x0 + 30, y0 + 135), tl, tf_, ts, ct, 1.1)
            sf, sl, ss = fit(d, it.get("sub", ""), "pop_r", 24, gw - 60, max(30, y0 + gh - yy - 25), min_size=18, max_lines=3)
            lines_at(d, (x0 + 30, yy + 8), sl, sf, ss, hexc(t["muted"]) if t["dark"] else hexc("#5E6673"))
    elif lay == "timeline":
        gap = (bot - top) / n
        d.line([(124, top + gap / 2), (124, top + gap * (n - .5))], fill=hexc(t["gold"]), width=6)
        for i, it in enumerate(items):
            cy = top + gap * i + gap / 2
            d.ellipse([84, cy - 40, 164, cy + 40], fill=hexc(t["accent"]), outline=hexc(t["gold"]), width=5)
            d.text((124, cy), str(i + 1), font=F("int_k", 40), fill="white", anchor="mm")
            tf_, tl, ts = fit(d, it.get("title", ""), t["title"], 44, W - 340, gap * .45, min_size=28, max_lines=1)
            d.text((200, cy - 6), tl[0] if tl else "", font=tf_, fill=hexc(t["text"]), anchor="ls")
            sf, sl, ss = fit(d, it.get("sub", ""), "pop_r", 28, W - 340, gap * .4, min_size=19, max_lines=2)
            lines_at(d, (200, cy + 10), sl, sf, ss, hexc(t["muted"]), 1.2)
            icon_circle(img, t, W - 110, int(cy), 36, it.get("icon"), ring=False)
    elif lay == "ceklis":
        gap = (bot - top) / n
        rh = min(124, gap - 22)
        for i, it in enumerate(items):
            cy = top + gap * i + gap / 2
            d.rounded_rectangle([60, cy - rh / 2, W - 60, cy + rh / 2], 20, fill=hexc(t["card"]))
            d.rounded_rectangle([92, cy - 30, 152, cy + 30], 10, outline=hexc(t["accent"]), width=6)
            d.line([(104, cy), (118, cy + 16), (146, cy - 22)], fill=hexc("#16A34A"), width=9)
            tf_, tl, ts = fit(d, it.get("title", ""), "pop_b", 40, W - 300, rh * .5, min_size=26, max_lines=1)
            d.text((182, cy - 6), tl[0] if tl else "", font=tf_, fill=ct, anchor="ls")
            sf, sl, ss = fit(d, it.get("sub", ""), "pop_r", 26, W - 300, rh * .32, min_size=18, max_lines=1)
            d.text((182, cy + 10), sl[0] if sl else "", font=sf, fill=sub_col(t), anchor="lt")
    else:  # kartu
        gap = (bot - top) / n
        rh = min(124, gap - 22)
        for i, it in enumerate(items):
            cy = top + gap * i + gap / 2
            y0, y1 = int(cy - rh / 2), int(cy + rh / 2)
            d.rounded_rectangle([60, y0, W - 60, y1], 26, fill=hexc(t["card"]))
            d.rectangle([60, y0 + 22, 70, y1 - 22], fill=hexc(t["gold"]))
            d.ellipse([92, cy - 32, 156, cy + 32], fill=hexc(t["accent"]))
            d.text((124, cy), str(i + 1), font=F("pop_b", 36), fill="white", anchor="mm")
            tf_, tl, ts = fit(d, it.get("title", ""), "pop_b", 42, 680, rh * .5, min_size=28, max_lines=1)
            sf, sl, ss = fit(d, it.get("sub", ""), "pop_r", 26, 680, rh * .32, min_size=19, max_lines=1)
            d.text((182, cy - 8), tl[0] if tl else "", font=tf_, fill=ct, anchor="ls")
            d.text((182, cy + 10), sl[0] if sl else "", font=sf, fill=sub_col(t), anchor="lt")
            icon_circle(img, t, W - 120, int(cy), int(min(42, rh / 2 - 12)), it.get("icon"))
    if note:
        d.ellipse([70, H - 150, 104, H - 116], fill=hexc(t["gold"]))
        d.text((87, H - 133), "i", font=F("pop_bi", 24), fill=hexc(t["bg"]), anchor="mm")
        f, ls, s = fit(d, note, "pop_i", 26, W - 200, 70, min_size=20, spacing=1.2, max_lines=2)
        lines_at(d, (122, H - 149), ls, f, s, hexc(t["muted"]), 1.2)
    return img


# ------------------------------------------------------------------ isi
def detail_slide(cfg, t, st, item, n, pillar, idx, total):
    img = background(t)
    chrome(img, t, cfg["brand"], pillar, idx, total)
    d = ImageDraw.Draw(img)
    lay = st["detail"]
    body = str(item.get("body", ""))
    title = item.get("title", "")
    is_prompt = body.strip().lower().startswith("prompt")
    name = cfg.get("influencer", {}).get("name", "Cicilia")

    if lay == "versus":
        d.rounded_rectangle([60, 170, W - 60, 560], 34, fill=hexc("#B91C1C"))
        d.line([(112, 222), (146, 256)], fill="white", width=8); d.line([(146, 222), (112, 256)], fill="white", width=8)
        d.text((170, 215), "MITOS", font=F("int_k", 44), fill="white")
        f, ls, s = fit(d, re.sub(r"^\s*mitos\s*:\s*", "", title, flags=re.I), "pop_b", 50, W - 220, 250, min_size=30, spacing=1.15)
        lines_at(d, (110, 290), ls, f, s, (255, 255, 255, 255), 1.15)
        d.rounded_rectangle([60, 600, W - 60, H - 150], 34, fill=hexc("#15803D"))
        d.line([(110, 670), (126, 688), (152, 652)], fill="white", width=8)
        d.text((170, 645), "FAKTA", font=F("int_k", 44), fill="white")
        f, ls, s = fit(d, re.sub(r"^\s*fakta\s*:\s*", "", body, flags=re.I), "pop_r", 44, W - 220, H - 150 - 730, min_size=26, spacing=1.35)
        lines_at(d, (110, 720), ls, f, s, (255, 255, 255, 255), 1.35)
        return img

    if lay == "chat":
        face = face_crop(st["pose"], st["flip"], st.get("expr"))
        code = re.sub(r'^\s*prompt\s*:\s*', '', body, flags=re.I).strip().strip('"“”') if is_prompt else body
        tf_, tl, ts = fit(d, title, "pop_b", 56, W - 260, 220, min_size=32, spacing=1.12, max_lines=3)
        bf, bl, bs = fit(d, code, "mono" if is_prompt else "pop_r", 42 if is_prompt else 50, W - 300, 560, min_size=24, spacing=1.4)
        bh = int(len(tl) * ts * 1.12 + 70)
        ch = int(len(bl) * bs * 1.4 + (130 if is_prompt else 80))
        total_h = 150 + bh + 34 + ch
        y0 = max(170, int((H - 120 - total_h) / 2 + 30))
        portrait(img, t, face, 150, y0 + 60, 64)
        d.text((240, y0 + 25), name, font=F("pop_b", 32), fill=hexc(t["text"]))
        d.text((240, y0 + 68), "virtual influencer AI • ASN GO", font=F("pop_r", 22), fill=hexc(t["muted"]))
        y = y0 + 160
        d.rounded_rectangle([90, y, W - 90, y + bh], 36, fill=hexc(t["card"]))
        d.polygon([(130, y + 2), (175, y + 2), (125, y - 32)], fill=hexc(t["card"]))
        lines_at(d, (130, y + 35), tl, tf_, ts, hexc(t["card_text"]), 1.12)
        y += bh + 34
        if is_prompt:
            d.rounded_rectangle([90, y, W - 90, y + ch], 30, fill=hexc("#0F172A"))
            for i, c in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
                d.ellipse([130 + i * 34, y + 30, 152 + i * 34, y + 52], fill=hexc(c))
            d.text((W - 130, y + 41), "SALIN PROMPT", font=F("mono_b", 24), fill=hexc("#7CF3FF"), anchor="rm")
            lines_at(d, (130, y + 90), bl, bf, bs, hexc("#E2E8F0"), 1.4)
        else:
            d.rounded_rectangle([90, y, W - 90, y + ch], 36, fill=hexc(t["accent"]))
            lines_at(d, (130, y + 40), bl, bf, bs, (255, 255, 255, 255), 1.4)
        return img

    if lay == "angka":
        d.text((40, 120), f"{n:02d}", font=F("int_k", 380), fill=hexc(t["gold"], 60))
        f, ls, s = fit(d, title, t["title"], 72, W - 140, 300, min_size=42, spacing=1.1)
        y = lines_at(d, (70, 470), ls, f, s, hexc(t["text"]), 1.1) + 30
        d.rectangle([70, y, 230, y + 10], fill=hexc(t["accent"]))
        f, ls, s = fit(d, body, "mono" if is_prompt else "pop_r", 46, W - 140, H - 200 - y - 60, min_size=26, spacing=1.42)
        lines_at(d, (70, y + 50), ls, f, s, hexc(t["text"]), 1.42)
        icon_circle(img, t, W - 150, 280, 70, item.get("icon"))
        return img

    # kartu
    pad = 56
    top_off = 116 if is_prompt else pad
    tf_, tl, ts = fit(d, title, t["title"], 70, W - 140, 260, min_size=42, spacing=1.15)
    bf, bl, bs = fit(d, body, "mono" if is_prompt else "pop_r", 44 if is_prompt else 48, W - 120 - pad * 2, 620, min_size=26, spacing=1.4)
    card_h = top_off + len(bl) * bs * 1.4 + pad
    block = 130 + 36 + len(tl) * ts * 1.15 + 40 + card_h
    y0 = max(160, (H - 140 - block) / 2 + 40)
    d.ellipse([70, y0, 200, y0 + 130], fill=hexc(t["accent"]))
    d.text((135, y0 + 65), str(n), font=F("pop_b", 70), fill="white", anchor="mm")
    if item.get("icon"):
        icon_circle(img, t, 262, int(y0 + 65), 48, item.get("icon"))
    y = lines_at(d, (70, y0 + 166), tl, tf_, ts, hexc(t["text"]), 1.15) + 40
    fill = hexc("#0F172A") if is_prompt else hexc(t["card"])
    txt = hexc("#E2E8F0") if is_prompt else hexc(t["card_text"])
    d.rounded_rectangle([60, y, W - 60, y + card_h], 36, fill=fill)
    if is_prompt:
        d.rounded_rectangle([60 + pad, y + 36, 60 + pad + 230, y + 86], 25, fill=hexc(t["accent"]))
        d.text((60 + pad + 115, y + 61), "SALIN PROMPT", font=F("pop_b", 23), fill="white", anchor="mm")
    else:
        d.rectangle([60, y + 40, 72, y + min(card_h - 40, 160)], fill=hexc(t["gold"]))
    lines_at(d, (60 + pad, y + top_off), bl, bf, bs, txt, 1.4)
    return img


# ------------------------------------------------------------------ penutup
def cta_slide(cfg, t, st, content, product, pillar, total):
    img = background(t)
    d = ImageDraw.Draw(img)
    name = cfg.get("influencer", {}).get("name")
    if st["cta"] == "badan":
        person, stem = load_pose(st["pose"], st["flip"])
        if person is not None:
            place_person(img, person, 700, 790, H - 26, t["glow"])
    else:
        portrait(img, t, face_crop(st["pose"], not st["flip"], st.get("expr")), W - 230, H - 330, 150)
    chrome(img, t, cfg["brand"], pillar, total - 1, total)
    d.text((W / 2, 230), "BERMANFAAT?", font=F(t["title"], 88), fill=hexc(t["text"]), anchor="mm")
    cf, cl, cs = fit(d, content.get("cta", "Simpan & bagikan ke rekan kerja!"), "pop_m", 42, W - 200, 130)
    y = 305
    for ln in cl:
        d.text((W / 2, y), ln, font=cf, fill=hexc(t["muted"]), anchor="ma")
        y += cs * 1.3
    y += 26
    for i, (label, col) in enumerate((("SIMPAN", t["gold"]), ("BAGIKAN", t["accent"]), ("FOLLOW", t["text"]))):
        x = 110 + i * 300
        d.rounded_rectangle([x, y, x + 260, y + 86], 43, outline=hexc(col), width=4)
        d.text((x + 130, y + 43), label, font=F("pop_b", 32), fill=hexc(col), anchor="mm")
    y += 140
    if product:
        pf, pl, ps = fit(d, product["name"], "pop_b", 46, 450, 120, min_size=30, spacing=1.08, max_lines=2)
        box_h = int(72 + len(pl) * ps * 1.08 + 60 + 90)
        d.rounded_rectangle([60, y, 590, y + box_h], 32, fill=hexc("#FFFFFF", 245), outline=hexc(t["accent"]), width=3)
        d.text((96, y + 32), "TOOLS PILIHAN", font=F("pop_b", 24), fill=hexc(t["accent"]))
        yy = lines_at(d, (96, y + 70), pl, pf, ps, hexc("#0B1F3A"), 1.08)
        d.text((96, yy + 4), product["price"].split(" (")[0], font=F("pop_b", 36), fill=hexc("#12305A"))
        d.rounded_rectangle([96, yy + 64, 340, yy + 114], 25, fill=hexc(t["accent"]))
        d.text((218, yy + 89), "Link di bio", font=F("pop_b", 24), fill="white", anchor="mm")
    else:
        d.text((330, y + 140), cfg["brand"]["handle"], font=F("pop_b", 52), fill=hexc(t["gold"]), anchor="mm")
    if name:
        d.text((70, H - 150), f"Salam digital, {name}", font=F("pop_i", 26), fill=hexc(t["muted"]))
    return img


# ------------------------------------------------------------------ orkestrasi
def render(cfg, state, draft_id, content, pillar_name, fmt, product=None, scene=None, pillar_id=None):
    pid = pillar_id or next((p["id"] for p in cfg["pillars"] if p["name"] == pillar_name), "asn")
    st = choose_style(state, draft_id, pid, fmt, content)
    t = THEMES[st["theme"]]
    state.work("desain", f"Mendesain gaya {st['theme']}/{st['cover']}/{st['list']}/{st['detail']}...")
    note = content.get("note")
    items = (content.get("items") or [])[:6]
    details = (content.get("details") or [])[:6]
    for i, it in enumerate(details):
        if not it.get("icon"):
            m = next((x for x in items if x.get("title", "").lower() == it.get("title", "").lower()), None)
            it["icon"] = (m or (items[i] if i < len(items) else {})).get("icon")
    total = min(10, 1 + (1 if items else 0) + len(details) + 1)
    details = details[: total - 2 - (1 if items else 0)]
    imgs = [cover(cfg, t, st, content, pillar_name, total, scene=scene)]
    if items:
        imgs.append(list_slide(cfg, t, st, items, note, pillar_name, 1, total))
    for i, it in enumerate(details, 1):
        imgs.append(detail_slide(cfg, t, st, it, i, pillar_name, len(imgs), total))
    imgs.append(cta_slide(cfg, t, st, content, product, pillar_name, total))
    out = PUBLIC / draft_id
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, im in enumerate(imgs, 1):
        p = out / f"slide_{i:02d}.jpg"
        im.convert("RGB").save(p, "JPEG", quality=90)
        paths.append(str(p.relative_to(ROOT)))
    state.done("desain", f"{len(paths)} slide gaya {st['theme']} siap")
    return paths
