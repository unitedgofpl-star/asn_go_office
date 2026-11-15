"""Mas Desain — carousel 1080x1350 (4:5) gaya ASN GO: navy, motif kawung emas, strip merah-putih,
dengan virtual influencer Cicilia di cover & penutup. Gratis: Pillow + pose di assets/influencer/.
Opsional: foto cover baru dari Gemini Image (lihat agents/foto.py)."""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

from ..core import ROOT, PUBLIC

W, H = 1080, 1350
FONTS = ROOT / "assets" / "fonts"
POSES = ROOT / "assets" / "influencer"
EMOJI_PATHS = ["/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", str(FONTS / "NotoColorEmoji.ttf")]


def F(weight, size):
    return ImageFont.truetype(str(FONTS / f"Poppins-{weight}.ttf"), size)


def hexc(h, a=255):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


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


def fit(draw, text, weight, size, width, max_h, min_size=24, spacing=1.25, max_lines=99):
    while size >= min_size:
        font = F(weight, size)
        lines = wrap(draw, text, font, width)
        if len(lines) * size * spacing <= max_h and len(lines) <= max_lines:
            return font, lines, size
        size -= 2
    font = F(weight, min_size)
    return font, wrap(draw, text, font, width)[:max_lines], min_size


def draw_lines(draw, xy, lines, font, size, fill, spacing=1.25, anchor=None):
    x, y = xy
    for ln in lines:
        draw.text((x, y), ln, font=font, fill=fill, anchor=anchor)
        y += size * spacing
    return y


# ------------------------------------------------------------------ dasar desain awal
def background(c):
    img = Image.new("RGBA", (W, H), hexc(c["bg"]))
    grad = Image.new("RGBA", (W, H))
    g = ImageDraw.Draw(grad)
    b1, b2 = hexc(c["bg"]), hexc(c["bg2"])
    for y in range(H):
        t = y / H
        g.line([(0, y), (W, y)], fill=tuple(int(b1[i] + (b2[i] - b1[i]) * t) for i in range(3)) + (255,))
    img = Image.alpha_composite(img, grad)
    # motif batik kawung di pojok
    pat = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    p = ImageDraw.Draw(pat)
    gold = hexc(c["gold"], 26)
    s = 90
    for gx in range(0, W + s, s):
        for gy in range(0, H + s, s):
            if math.hypot(gx - W, gy) < 520 or math.hypot(gx, gy - H) < 420:
                r = s * 0.42
                for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                    ex, ey = gx + dx * r * 0.55, gy + dy * r * 0.55
                    rx, ry = (r * 0.5, r * 0.28) if dx else (r * 0.28, r * 0.5)
                    p.ellipse([ex - rx, ey - ry, ex + rx, ey + ry], outline=gold, width=3)
                p.ellipse([gx - 6, gy - 6, gx + 6, gy + 6], fill=gold)
    img = Image.alpha_composite(img, pat)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([-300, -300, 600, 500], fill=hexc(c["accent"], 40))
    return Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(160)))


def chrome(img, c, brand, pillar_name, idx, total):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([60, 56, 116, 112], 14, fill=hexc(c["accent"]))
    d.text((88, 84), "AG", font=F("Bold", 24), fill="white", anchor="mm")
    d.text((132, 62), brand["name"], font=F("Bold", 28), fill=hexc(c["text"]))
    d.text((132, 94), brand["handle"], font=F("Regular", 22), fill=hexc(c["muted"]))
    tag = pillar_name.upper()
    tf = F("Medium", 22)
    tw = d.textlength(tag, font=tf)
    d.rounded_rectangle([W - 60 - tw - 40, 64, W - 60, 106], 21, fill=hexc(c["bg"], 170), outline=hexc(c["gold"]), width=2)
    d.text((W - 60 - tw / 2 - 20, 85), tag, font=tf, fill=hexc(c["gold"]), anchor="mm")
    x0 = (W - total * 22) / 2
    for i in range(total):
        col = hexc(c["gold"]) if i == idx else hexc(c["muted"], 90)
        r = 7 if i == idx else 5
        cx = x0 + i * 22 + 11
        d.ellipse([cx - r, H - 92 - r, cx + r, H - 92 + r], fill=col)
    d.rectangle([0, H - 26, W / 2, H], fill=hexc("#E63946"))
    d.rectangle([W / 2, H - 26, W, H], fill=hexc("#FFFFFF"))
    if idx < total - 1:
        d.text((W - 90, H - 92), "geser", font=F("Medium", 24), fill=hexc(c["muted"]), anchor="rm")
        d.polygon([(W - 80, H - 102), (W - 60, H - 92), (W - 80, H - 82)], fill=hexc(c["gold"]))


def emoji_tile(ch, size):
    for p in EMOJI_PATHS:
        if Path(p).exists():
            try:
                f = ImageFont.truetype(p, 109)
                t = Image.new("RGBA", (136, 128), (0, 0, 0, 0))
                ImageDraw.Draw(t).text((68, 64), ch, font=f, embedded_color=True, anchor="mm")
                t = t.crop(t.getbbox() or (0, 0, 136, 128))
                t.thumbnail((size, size), Image.LANCZOS)
                return t
            except Exception:
                pass
    return None


def icon_circle(img, c, cx, cy, r, icon):
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4], fill=hexc(c["gold"]))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=hexc("#FFF6E6"))
    t = emoji_tile(icon, int(r * 1.1)) if icon else None
    if t:
        img.alpha_composite(t, (int(cx - t.width / 2), int(cy - t.height / 2)))
    elif icon:
        d.text((cx, cy), str(icon)[:2], font=F("Bold", int(r * .8)), fill=hexc(c["bg"]), anchor="mm")


def place_person(img, person, height, cx, bottom, glow_col=(244, 185, 66)):
    p = person.copy()
    s = height / p.height
    p = p.resize((int(p.width * s), int(p.height * s)), Image.LANCZOS)
    x, y = int(cx - p.width / 2), int(bottom - p.height)
    halo = Image.new("RGBA", p.size, glow_col + (0,))
    halo.putalpha(p.split()[3].filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(v * .55)))
    img.alpha_composite(halo, (x, y))
    img.alpha_composite(p, (x, y))


def load_pose(name, fallback="melipat_tangan"):
    f = POSES / f"{name}.png"
    if not f.exists():
        f = POSES / f"{fallback}.png"
    if not f.exists():
        return None, None
    p = Image.open(f).convert("RGBA")
    if f.stem == "berdiri":  # setengah badan agar wajah besar
        p = p.crop((0, 0, p.width, int(p.height * .58)))
    return p, f.stem


def footnote(img, c, text, y=H - 150):
    d = ImageDraw.Draw(img)
    f, lines, s = fit(d, "ⓘ " + text if False else text, "Italic", 26, W - 200, 70, min_size=20, spacing=1.2, max_lines=2)
    d.ellipse([70, y, 104, y + 34], fill=hexc(c["gold"]))
    d.text((87, y + 17), "i", font=F("BoldItalic", 24), fill=hexc(c["bg"]), anchor="mm")
    draw_lines(d, (122, y + 1), lines, f, s, hexc(c["muted"]), spacing=1.2)


# ------------------------------------------------------------------ slide
def cover(cfg, content, pillar, total, scene=None):
    c, brand = cfg["brand"]["colors"], cfg["brand"]
    img = background(c)
    if scene is not None:  # foto AI (mode Gemini) di bagian bawah, menyatu dengan navy
        s = max(W / scene.width, 900 / scene.height)
        sc = scene.convert("RGBA").resize((int(scene.width * s), int(scene.height * s)), Image.LANCZOS)
        sc = sc.crop(((sc.width - W) // 2, sc.height - 900, (sc.width - W) // 2 + W, sc.height))
        mask = Image.new("L", (W, 900), 255)
        md = ImageDraw.Draw(mask)
        for y in range(260):
            md.line([(0, y), (W, y)], fill=int(255 * y / 260))
        img.paste(sc, (0, H - 900), mask)
    else:
        person, stem = load_pose(content.get("cover_pose", "melipat_tangan"))
        if person is not None:
            hgt = 760 if stem != "presentasi" else 640
            place_person(img, person, hgt, 760 + (40 if stem == "presentasi" else 0), H - 26)
    d = ImageDraw.Draw(img)
    chrome(img, c, brand, pillar, 0, total)
    # judul
    font, lines, size = fit(d, content["hook"].upper(), "Bold", 96, W - 140, 400, min_size=56, spacing=1.1, max_lines=4)
    y = 170
    for ln in lines:
        d.text((73, y + 4), ln, font=font, fill=(0, 0, 0, 120))
        d.text((70, y), ln, font=font, fill=hexc(c["text"]))
        y += size * 1.1
    d.rounded_rectangle([70, y + 14, 250, y + 26], 6, fill=hexc(c["gold"]))
    if content.get("subtitle"):
        sf, sl, ss = fit(d, content["subtitle"], "Regular", 36, 520, 140)
        draw_lines(d, (70, y + 50), sl, sf, ss, hexc(c["muted"]))
    # pill & nama influencer
    name = cfg.get("influencer", {}).get("name")
    d.rounded_rectangle([70, H - 290, 400, H - 214], 38, fill=hexc(c["accent"]))
    d.text((235, H - 252), "SIMPAN DULU", font=F("Bold", 30), fill="white", anchor="mm")
    if name:
        d.text((72, H - 190), f"bareng {name} • ilustrasi AI", font=F("Italic", 22), fill=hexc(c["muted"]))
    return img


def list_slide(cfg, items, note, pillar, idx, total):
    c, brand = cfg["brand"]["colors"], cfg["brand"]
    img = background(c)
    chrome(img, c, brand, pillar, idx, total)
    d = ImageDraw.Draw(img)
    n = max(len(items), 1)
    top, bot = 150, H - 190 if note else H - 130
    gap = (bot - top) / n
    rh = min(124, gap - 22)
    for i, it in enumerate(items):
        cy = top + gap * i + gap / 2
        y0, y1 = int(cy - rh / 2), int(cy + rh / 2)
        d.rounded_rectangle([60, y0, W - 60, y1], 26, fill=hexc(c["bg2"], 235))
        d.rectangle([60, y0 + 22, 70, y1 - 22], fill=hexc(c["gold"]))
        d.ellipse([92, cy - 32, 156, cy + 32], fill=hexc(c["accent"]))
        d.text((124, cy), str(i + 1), font=F("Bold", 36), fill="white", anchor="mm")
        tf, tl, ts = fit(d, it.get("title", ""), "Bold", 42, 680, rh * .5, min_size=28, max_lines=1)
        sf, sl, ss = fit(d, it.get("sub", ""), "Regular", 26, 680, rh * .32, min_size=19, max_lines=1)
        d.text((182, cy - 8), tl[0] if tl else "", font=tf, fill=hexc(c["text"]), anchor="ls")
        d.text((182, cy + 10), sl[0] if sl else "", font=sf, fill=hexc(c["muted"]), anchor="lt")
        icon_circle(img, c, W - 120, int(cy), int(min(42, rh / 2 - 12)), it.get("icon"))
    if note:
        footnote(img, c, note)
    return img


def detail_slide(cfg, item, n, pillar, idx, total, note=None):
    c, brand = cfg["brand"]["colors"], cfg["brand"]
    img = background(c)
    chrome(img, c, brand, pillar, idx, total)
    d = ImageDraw.Draw(img)
    pad = 54
    body = str(item.get("body", ""))
    is_prompt = body.strip().lower().startswith("prompt")
    top_off = 116 if is_prompt else pad
    tf, tl, ts = fit(d, item.get("title", ""), "Bold", 70, W - 140, 260, min_size=42, spacing=1.15)
    title_h = len(tl) * ts * 1.15
    bottom_lim = H - 200 if note else H - 140
    bf, bl, bs = fit(d, body, "Regular", 48, W - 120 - pad * 2, 620, min_size=28, spacing=1.4)
    card_h = top_off + len(bl) * bs * 1.4 + pad
    block = 130 + 36 + title_h + 40 + card_h
    y0 = max(160, (bottom_lim - block) / 2 + 60)
    d.ellipse([70, y0, 200, y0 + 130], fill=hexc(c["accent"]))
    d.text((135, y0 + 65), str(n), font=F("Bold", 70), fill="white", anchor="mm")
    if item.get("icon"):
        icon_circle(img, c, 262, int(y0 + 65), 48, item.get("icon"))
    y = draw_lines(d, (70, y0 + 166), tl, tf, ts, hexc(c["text"]), spacing=1.15) + 40
    fill = hexc("#FFFFFF", 240) if is_prompt else hexc(c["bg2"], 235)
    txt = hexc("#0B1F3A") if is_prompt else hexc(c["text"])
    d.rounded_rectangle([60, y, W - 60, y + card_h], 36, fill=fill)
    if is_prompt:
        d.rounded_rectangle([60 + pad, y + 36, 60 + pad + 230, y + 86], 25, fill=hexc(c["accent"]))
        d.text((60 + pad + 115, y + 61), "SALIN PROMPT", font=F("Bold", 23), fill="white", anchor="mm")
    else:
        d.rectangle([60, y + 40, 72, y + min(card_h - 40, 160)], fill=hexc(c["gold"]))
    draw_lines(d, (60 + pad, y + top_off), bl, bf, bs, txt, spacing=1.4)
    if note:
        footnote(img, c, note)
    return img


def cta_slide(cfg, content, product, pillar, total):
    c, brand = cfg["brand"]["colors"], cfg["brand"]
    img = background(c)
    person, stem = load_pose("presentasi")
    if person is not None:
        place_person(img, person, 700, 790, H - 26)
    d = ImageDraw.Draw(img)
    chrome(img, c, brand, pillar, total - 1, total)
    d.text((W / 2, 230), "BERMANFAAT?", font=F("Bold", 88), fill=hexc(c["text"]), anchor="mm")
    cf, cl, cs = fit(d, content.get("cta", "Simpan & bagikan ke rekan kerja!"), "Medium", 42, W - 200, 130)
    y = 305
    for ln in cl:
        d.text((W / 2, y), ln, font=cf, fill=hexc(c["muted"]), anchor="ma")
        y += cs * 1.3
    y += 26
    for i, (label, col) in enumerate((("SIMPAN", c["gold"]), ("BAGIKAN", c["accent"]), ("FOLLOW", "#FFFFFF"))):
        x = 110 + i * 300
        d.rounded_rectangle([x, y, x + 260, y + 86], 43, outline=hexc(col), width=4)
        d.text((x + 130, y + 43), label, font=F("Bold", 32), fill=hexc(col), anchor="mm")
    y += 140
    name = cfg.get("influencer", {}).get("name")
    if product:
        pf, pl, ps = fit(d, product["name"], "Bold", 48, 470, 120, min_size=32, spacing=1.08, max_lines=2)
        box_h = int(72 + len(pl) * ps * 1.08 + 60 + 90)
        d.rounded_rectangle([60, y, 600, y + box_h], 32, fill=hexc("#FFFFFF", 245))
        d.text((96, y + 32), "TOOLS PILIHAN", font=F("Bold", 24), fill=hexc(c["accent"]))
        yy = draw_lines(d, (96, y + 70), pl, pf, ps, hexc("#0B1F3A"), spacing=1.08)
        d.text((96, yy + 4), product["price"], font=F("Bold", 38), fill=hexc("#12305A"))
        d.rounded_rectangle([96, yy + 64, 340, yy + 114], 25, fill=hexc(c["accent"]))
        d.text((218, yy + 89), "Link di bio", font=F("Bold", 24), fill="white", anchor="mm")
    else:
        d.text((350, y + 140), brand["handle"], font=F("Bold", 52), fill=hexc(c["gold"]), anchor="mm")
    if name:
        d.text((70, H - 150), f"Salam digital, {name}", font=F("Italic", 26), fill=hexc(c["muted"]))
    return img


# ------------------------------------------------------------------ orkestrasi
def render(cfg, state, draft_id, content, pillar_name, fmt, product=None, scene=None):
    state.work("desain", "Mendesain carousel + Cicilia...")
    note = content.get("note")
    items = (content.get("items") or [])[:6]
    details = (content.get("details") or [])[:6]
    for i, it in enumerate(details):
        if not it.get("icon"):
            m = next((x for x in items if x.get("title", "").lower() == it.get("title", "").lower()), None)
            it["icon"] = (m or (items[i] if i < len(items) else {})).get("icon")
    total = min(10, 1 + (1 if items else 0) + len(details) + 1)
    details = details[: total - 2 - (1 if items else 0)]
    imgs = [cover(cfg, content, pillar_name, total, scene=scene)]
    if items:
        imgs.append(list_slide(cfg, items, note, pillar_name, 1, total))
    for i, it in enumerate(details, 1):
        imgs.append(detail_slide(cfg, it, i, pillar_name, len(imgs), total, note if i == len(details) and not items else None))
    imgs.append(cta_slide(cfg, content, product, pillar_name, total))
    out = PUBLIC / draft_id
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, im in enumerate(imgs, 1):
        p = out / f"slide_{i:02d}.jpg"
        im.convert("RGB").save(p, "JPEG", quality=90)
        paths.append(str(p.relative_to(ROOT)))
    state.done("desain", f"{len(paths)} slide siap (1080x1350)")
    return paths
