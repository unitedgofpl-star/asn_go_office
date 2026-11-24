"""Video gaya "promo kinetik" (seperti contoh Promo Simulasi CAT): klip Cicilia bergerak, teks muncul per kata
mengikuti suara, kotak penekanan kuning/merah, chip poin, lalu kartu penutup produk dengan harga.

Suara: narasi "Gadis" → diubah ke warna suara Cicilia (suara.kloning). Musik: lo-fi buatan sendiri.
"""
import math
import random
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from ..core import ROOT, PUBLIC
from .. import llm
from . import desain as D
from . import suara
from .tiktok import _ffmpeg

W, H, FPS = 1080, 1920, 30
CLIP_DIR = ROOT / "assets" / "video"
NAVY, RED, GOLD, WHITE = (11, 31, 58), (230, 57, 70), (244, 196, 48), (255, 255, 255)
MOOD_KLIP = {"ceria": ["c2", "c1", "a1"], "semangat": ["b3", "b2", "b4"], "terkejut": ["b4", "c1", "a1"],
             "tegas": ["b4", "b3", "b1"], "tenang": ["b1", "a1", "c2"], "menjelaskan": ["a1", "b2", "b1"],
             "sayang": ["c2", "c1"], "sedih": ["b1", "a1"], "cemberut": ["b1", "b4"]}

SCHEMA = """
Balas HANYA JSON:
{
 "hook": "judul sampul video, maks 8 kata, memancing rasa penasaran",
 "mood": "ceria|semangat|terkejut|tegas|tenang|menjelaskan",
 "scenes": [
   {"say": "1 kalimat narasi lisan 6-15 kata. Tandai 1-4 kata terpenting dengan [kurung siku], mis: Latihan rasa [ujian CAT asli] langsung dari HP.",
    "mood": "ceria|semangat|terkejut|tegas|tenang|menjelaskan",
    "chips": ["opsional: 2-4 poin super pendek (maks 4 kata), diawali angka bila ada. Hanya di SATU scene"]}
 ],
 "penutup_say": "kalimat ajakan akhir 8-18 kata (diucapkan di kartu penutup)",
 "penutup_tag": "slogan penutup maks 4 kata, huruf kapital",
 "caption": "caption IG/TikTok 2-4 paragraf pendek + ajakan",
 "hashtags": ["#..."]
}
Aturan: 3-5 scene, total narasi ±18-28 detik diucapkan. Kalimat lisan, santai, hangat ("Rekan ASN", "kamu").
Scene pertama = HOOK kuat (pertanyaan/masalah). Jangan memakai emoji di "say". Angka tulis dengan digit.
Jangan mengarang fitur/angka/harga yang tidak disebut di brief."""


def write_script(cfg, state, pillar, topic, product=None, promo=False, avoid=None):
    from .naskah import _system
    state.work("naskah", f"Menulis naskah video kinetik: {topic[:45]}")
    if promo and product:
        prompt = (f"Buat naskah VIDEO PROMOSI pendek (gaya TikTok promo, cepat & meyakinkan) untuk produk:\n"
                  f"Nama: {product['name']}\nHarga: {product['price']}\nFakta produk (HANYA pakai ini): {product.get('pitch', '')}\n"
                  "Alur: masalah sehari-hari ASN/perangkat desa → produk sebagai solusi → 2-4 keunggulan (chips) → "
                  "manfaat/hasil → penutup ajak klik link di bio & sebut harga.\n")
    else:
        prompt = (f"Pilar: {pillar['name']}\nTopik: {topic}\nBuat naskah VIDEO EDUKASI pendek (gaya TikTok, cepat & bertenaga): "
                  "hook masalah → 2-3 tips/fakta inti (boleh chips) → manfaat → penutup ajak simpan & follow.\n")
        if product:
            prompt += f"Penutup boleh menyebut singkat: {product['name']} ({product['price']}) — link di bio.\n"
    if avoid:
        prompt += "Jangan mengulang judul ini: " + "; ".join(avoid[-12:]) + "\n"
    sc = llm.ask(prompt + SCHEMA, _system(cfg), as_json=True)
    sc["scenes"] = [s for s in sc.get("scenes", []) if s.get("say")][:5] or [{"say": sc.get("hook", topic), "mood": "semangat"}]
    state.done("naskah", f"Naskah video: \"{sc.get('hook', '')}\"")
    return sc


# ------------------------------------------------------------------ teks & waktu per kata
def tokens(say):
    """'Latihan rasa [ujian CAT asli] dari HP' → [(kata, tekan:boolean), ...]"""
    out = []
    for part in re.split(r"(\[[^\]]+\])", say):
        tekan = part.startswith("[")
        for w in part.strip("[]").split():
            out.append((w, tekan))
    return out


def bersih(say):
    return re.sub(r"[\[\]]", "", say)


def bobot(word):
    sp = suara.ucapan(word) or word
    return max(1, len(re.findall(r"[aiueo]", sp.lower()))) + 0.6


def timing(toks, t0, t1):
    """Bagi waktu bicara [t0, t1] ke tiap kata sebanding jumlah suku katanya."""
    ws = [bobot(w) for w, _ in toks]
    tot = sum(ws)
    t, out = t0, []
    for w in ws:
        d = (t1 - t0) * w / tot
        out.append((t, t + d))
        t += d
    return out


def chunks(toks, times):
    """Kelompokkan kata jadi potongan teks layar: kata ditekan = 1 potongan sendiri, kata biasa maks 3."""
    res, cur = [], []
    for (w, tk), tm in zip(toks, times):
        if cur and (cur[-1][1] != tk or (not tk and len(cur) >= 3)):
            res.append(cur)
            cur = []
        cur.append((w, tk, tm))
    if cur:
        res.append(cur)
    # gabungkan potongan biasa + potongan tekan berikutnya jadi satu tampilan (2 baris seperti contoh)
    view, i = [], 0
    while i < len(res):
        a = res[i]
        if not a[0][1] and i + 1 < len(res) and res[i + 1][0][1]:
            view.append(a + res[i + 1])
            i += 2
        else:
            view.append(a)
            i += 1
    return view


# ------------------------------------------------------------------ gambar overlay
_FC = {}


def font(key, size):
    k = (key, size)
    if k not in _FC:
        _FC[k] = D.F(key, size)
    return _FC[k]


def caption_img(words, shown, ekor=None):
    """Gambar blok caption: baris biasa (putih bergaris) + kotak tekan (kuning/merah)."""
    biasa = [w for w, tk, _ in words if not tk]
    tekan = [w for w, tk, _ in words if tk]
    vis = words[:shown]
    vb = " ".join(w for w, tk, _ in vis if not tk)
    vt = " ".join(w for w, tk, _ in words if tk) if any(tk for _, tk, _ in vis) else ""  # kata tekan tampil sekaligus
    im = Image.new("RGBA", (W, 460), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    y = 10
    if biasa:
        f = font("pop_b", 76 if len(" ".join(biasa)) < 20 else 64)
        full = " ".join(biasa)
        x0 = (W - d.textlength(full, font=f)) / 2
        d.text((x0, y), vb, font=f, fill=WHITE, stroke_width=7, stroke_fill=(10, 20, 40, 210))
        y += int(f.size * 1.25)
    if tekan and vt:
        txt = " ".join(tekan).upper()
        f = font("int_k", 92 if len(txt) <= 14 else 78 if len(txt) <= 20 else 62)
        tw = d.textlength(txt, font=f)
        while tw > W - 120 and f.size > 40:
            f = font("int_k", f.size - 6)
            tw = d.textlength(txt, font=f)
        bg, fg = ekor or (GOLD, NAVY)
        x0 = (W - tw) / 2
        d.rounded_rectangle([x0 - 26, y, x0 + tw + 26, y + f.size * 1.22], 18, fill=bg + (255,))
        d.text((x0, y + f.size * 0.08), vt.upper(), font=f, fill=fg)
        y += int(f.size * 1.3)
    return im.crop((0, 0, W, max(20, y + 10)))


def chip_img(text):
    m = re.match(r"^([\d.,%+]+)\s*(.*)$", text.strip())
    num, rest = (m.group(1), m.group(2)) if m else ("", text.strip())
    fn, fr = font("int_k", 46), font("pop_m", 38)
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w = (d0.textlength(num, font=fn) + 14 if num else 0) + d0.textlength(rest, font=fr) + 56
    im = Image.new("RGBA", (int(w), 78), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, 77], 16, fill=(11, 31, 58, 225), outline=GOLD + (255,), width=3)
    x = 28
    if num:
        d.text((x, 39), num, font=fn, fill=GOLD, anchor="lm")
        x += d.textlength(num, font=fn) + 14
    d.text((x, 41), rest, font=fr, fill=WHITE, anchor="lm")
    return im


def badge(cfg):
    """Pita merah-putih + lencana merek di kanan atas (sekaligus menutup lencana lama di klip)."""
    im = Image.new("RGBA", (W, 270), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W * 0.62, 22], fill=RED + (255,))
    d.rectangle([W * 0.62, 0, W, 22], fill=WHITE + (255,))
    d.rounded_rectangle([764, 22, W + 60, 256], 50, fill=(11, 31, 58, 255))
    d.rectangle([900, 22, W, 70], fill=(11, 31, 58, 255))
    d.rounded_rectangle([790, 104, 902, 216], 24, fill=WHITE + (255,))
    d.rounded_rectangle([800, 114, 892, 206], 18, fill=RED + (255,))
    d.text((846, 160), "AG", font=font("int_k", 46), fill=WHITE, anchor="mm")
    nm = cfg["brand"]["name"].split()
    d.text((918, 118), " ".join(nm[:2]) if len(nm) > 2 else nm[0], font=font("pop_b", 38), fill=WHITE)
    d.text((918, 166), " ".join(nm[2:]) if len(nm) > 2 else " ".join(nm[1:]), font=font("pop_b", 32), fill=GOLD)
    return im


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def paste_scaled(base, im, cx, cy, s, alpha=1.0):
    if s != 1.0:
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BILINEAR)
    if alpha < 1.0:
        a = im.split()[3].point(lambda v: int(v * alpha))
        im = im.copy()
        im.putalpha(a)
    base.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


# ------------------------------------------------------------------ kartu penutup
def _doc_card(w, h, judul):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], 34, fill=(20, 24, 33, 255))
    d.rounded_rectangle([12, 12, w - 13, h - 13], 26, fill=(250, 250, 252, 255))
    d.rectangle([40, 60, w - 40, 66], fill=NAVY + (255,))
    d.text((w / 2, 44), "PEMERINTAH KABUPATEN", font=font("pop_b", 15), fill=NAVY, anchor="mm")
    d.text((w / 2, 96), judul, font=font("pop_b", 20), fill=NAVY, anchor="mm")
    y = 130
    for i in range(9):
        d.rounded_rectangle([40, y, w - 40 - (60 if i % 3 == 2 else 0), y + 9], 4, fill=(200, 206, 218, 255))
        y += 26
    d.rounded_rectangle([w - 170, h - 120, w - 40, h - 60], 10, outline=(41, 98, 255, 255), width=3)
    d.text((w - 105, h - 90), "TTE", font=font("pop_b", 22), fill=(41, 98, 255), anchor="mm")
    return im


def end_card(cfg, sc, product, harga_txt, ket_txt, t, promo):
    """Kartu penutup; t = detik sejak kartu muncul (untuk animasi masuk)."""
    im = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(im)
    for i in range(0, H, 6):  # gradasi
        k = i / H
        d.rectangle([0, i, W, i + 6], fill=(int(11 + 20 * k), int(31 + 40 * (1 - k)), int(58 + 70 * (1 - abs(.5 - k) * 2)), 255))
    for j in range(5):  # garis cahaya diagonal
        x = -400 + j * 380 + (t * 60) % 380
        d.polygon([(x, H), (x + 120, H), (x + 900, 0), (x + 780, 0)], fill=(255, 255, 255, 10))
    a1, a2, a3 = ease(t / .35), ease((t - .2) / .4), ease((t - .45) / .4)
    # ikon + nama
    ic = Image.new("RGBA", (190, 190), (0, 0, 0, 0))
    di = ImageDraw.Draw(ic)
    di.rounded_rectangle([0, 0, 189, 189], 42, fill=WHITE + (255,))
    di.rounded_rectangle([46, 28, 144, 160], 10, fill=(232, 238, 248, 255), outline=NAVY + (255,), width=5)
    for k in range(4):
        di.rectangle([62, 56 + k * 22, 128 - (20 if k == 3 else 0), 64 + k * 22], fill=NAVY + (255,))
    di.rounded_rectangle([96, 118, 166, 170], 12, fill=RED + (255,))
    di.text((131, 144), "AI", font=font("int_k", 30), fill=WHITE, anchor="mm")
    paste_scaled(im, ic, W / 2, 250, 0.6 + 0.4 * a1, a1)
    d = ImageDraw.Draw(im)
    nama = product["name"] if (promo and product) else "Simpan & bagikan"
    f = font("pop_b", 64)
    while d.textlength(nama, font=f) > W - 120 and f.size > 40:
        f = font("pop_b", f.size - 4)
    d.text((W / 2, 410), nama, font=f, fill=WHITE + (int(255 * a1),), anchor="mm")
    tag = (sc.get("penutup_tag") or ("SURAT DINAS 1 MENIT" if promo else "FOLLOW BIAR NGGAK KETINGGALAN")).upper()[:30]
    ft = font("int_k", 50)
    tw = d.textlength(tag, font=ft)
    d.rounded_rectangle([W / 2 - tw / 2 - 26, 460, W / 2 + tw / 2 + 26, 532], 14, fill=RED + (int(255 * a1),))
    d.text((W / 2, 496), tag, font=ft, fill=WHITE + (int(255 * a1),), anchor="mm")
    if promo and product:
        for k, (dx, ang, judul) in enumerate([(-190, 6, "SURAT UNDANGAN"), (190, -6, "NOTA DINAS")]):
            card = _doc_card(420, 640, judul).rotate(ang, expand=True, resample=Image.BICUBIC)
            paste_scaled(im, card, W / 2 + dx, 930 + 160 * (1 - a2), 1.0, a2)
        d = ImageDraw.Draw(im)
        if harga_txt:
            pulse = 1 + 0.035 * math.sin(t * 6) if t > 1 else 1.0
            box = Image.new("RGBA", (700, 200), (0, 0, 0, 0))
            db = ImageDraw.Draw(box)
            db.rounded_rectangle([0, 0, 699, 199], 30, fill=GOLD + (255,))
            db.text((350, 82), harga_txt, font=font("int_k", 104), fill=NAVY, anchor="mm")
            db.text((350, 160), ket_txt, font=font("pop_m", 32), fill=NAVY, anchor="mm")
            paste_scaled(im, box.rotate(-3, expand=True, resample=Image.BICUBIC), W / 2, 1290, (0.7 + 0.3 * a3) * pulse, a3)
            d = ImageDraw.Draw(im)
    else:
        pts = [p for p in (sc.get("end_points") or []) if p][:3] or ["Simpan video ini", "Bagikan ke rekan kerja", f"Follow {cfg['brand']['handle']}"]
        y = 700
        for k, p in enumerate(pts):
            ak = ease((t - .2 - k * .15) / .35)
            d.rounded_rectangle([140, y, W - 140, y + 120], 26, fill=(255, 255, 255, int(28 * ak)), outline=GOLD + (int(255 * ak),), width=3)
            d.text((200, y + 60), f"{k + 1}", font=font("int_k", 52), fill=GOLD + (int(255 * ak),), anchor="mm")
            d.text((250, y + 60), p[:30], font=font("pop_b", 42), fill=WHITE + (int(255 * ak),), anchor="lm")
            y += 150
        if product and harga_txt:
            d.text((W / 2, 1230), f"Butuh surat dinas cepat? {product['name']}", font=font("pop_m", 32), fill=(220, 228, 240, int(255 * a3)), anchor="mm")
            d.text((W / 2, 1280), f"mulai {harga_txt}", font=font("int_k", 46), fill=GOLD + (int(255 * a3),), anchor="mm")
    # tombol & tautan
    fb = font("int_k", 46)
    lbl = "KLIK LINK DI BIO"
    bw = d.textlength(lbl, font=fb) + 90
    d.rounded_rectangle([W / 2 - bw / 2, 1440, W / 2 + bw / 2, 1530], 22, fill=RED + (int(255 * a3),))
    d.text((W / 2, 1485), lbl, font=fb, fill=WHITE + (int(255 * a3),), anchor="mm")
    url = re.sub(r"^https?://", "", cfg.get("lynk_url", ""))
    d.text((W / 2, 1572), url, font=font("pop_b", 32), fill=WHITE + (int(255 * a3),), anchor="mm")
    if promo and cfg.get("landing_url"):
        d.text((W / 2, 1618), "Info lengkap: " + re.sub(r"^https?://", "", cfg["landing_url"]), font=font("pop_r", 24),
               fill=(200, 210, 228, int(255 * a3)), anchor="mm")
    return im


# ------------------------------------------------------------------ perakitan
def _klip_dur(p):
    return suara.duration(p) or 1.5


def base_video(scenes, total, end_start, out, seed):
    """Video dasar: potongan klip Cicilia sesuai mood tiap scene (zoom pelan), lalu latar gelap untuk kartu penutup."""
    rnd = random.Random(seed)
    klip = {p.stem.split("_")[-1]: p for p in CLIP_DIR.glob("cicilia_*.mp4")}
    segs, last = [], None
    for sc in scenes:
        need = sc["dur"]
        pool = [k for k in MOOD_KLIP.get(sc.get("mood", "semangat"), list(klip)) if k in klip and k != last] or [k for k in klip if k != last]
        while need > 0.05:
            k = rnd.choice(pool[:2]) if len(pool) > 1 else pool[0]
            ln = _klip_dur(klip[k])
            slow = min(1.45, max(1.0, need / ln))
            d = min(need, ln * slow)
            if need - d < 0.6:  # sisa terlalu pendek → panjangkan potongan ini (perlambat sedikit)
                d = need
                slow = max(slow, d / ln)
            segs.append((klip[k], slow, d))
            need -= d
            last = k
            pool = [x for x in klip if x != last]
    tail = total - end_start
    cmd = [_ffmpeg(), "-y", "-loglevel", "error"]
    parts = []
    for i, (p, slow, d) in enumerate(segs):
        cmd += ["-i", str(p)]
        z0, z1 = (1.0, 1.07) if i % 2 == 0 else (1.07, 1.0)
        parts.append(f"[{i}:v]setpts={slow:.3f}*PTS,tpad=stop_mode=clone:stop_duration=3,trim=duration={d:.3f},setpts=PTS-STARTPTS,"
                     f"scale=w='trunc({W}*({z0}+({z1}-{z0})*t/{d:.3f})/2)*2':h=-2:eval=frame,crop={W}:{H},fps={FPS},setsar=1,format=yuv420p[s{i}]")
    n = len(segs)
    cmd += ["-f", "lavfi", "-i", f"color=c=0x0B1F3A:s={W}x{H}:r={FPS}:d={tail:.3f}"]
    parts.append(f"[{n}:v]format=yuv420p,setsar=1[s{n}]")
    parts.append("".join(f"[s{i}]" for i in range(n + 1)) + f"concat=n={n + 1}:v=1:a=0[v]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(FPS), str(out)]
    subprocess.run(cmd, check=True)


def render(cfg, state, draft_id, sc, product=None, promo=False, seed=0):
    from .. import harga
    state.work("desain", "Merekam suara Cicilia untuk video...")
    tmp = Path(tempfile.mkdtemp())
    out_dir = PUBLIC / draft_id
    out_dir.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(seed)
    s_cfg = cfg.get("suara", {})

    # 1) narasi per scene (suara Gadis) → satu trek dengan jeda → diubah ke suara Cicilia
    scenes = [dict(x) for x in sc["scenes"]]
    lines = [bersih(x["say"]) for x in scenes] + [sc.get("penutup_say") or "Klik link di bio, ya!"]
    vd = []
    for i, txt in enumerate(lines):
        vd.append(suara.tts(cfg, txt, tmp / f"n{i}.mp3"))
    gap, lead = 0.28, 0.15
    t = lead
    for i, x in enumerate(scenes):
        x["t0"], x["speech"] = t, max(vd[i], 1.6)
        x["dur"] = x["speech"] + gap + (lead if i == 0 else 0)
        t += x["speech"] + gap
    end_start = t
    end_speech = max(vd[-1], 2.0)
    total = end_start + end_speech + 1.4
    scenes[0]["dur"] = scenes[0]["t0"] + scenes[0]["speech"] + gap
    # trek narasi
    inputs, filt, labs = [], [], []
    starts = [x["t0"] for x in scenes] + [end_start + 0.25]
    for i, d in enumerate(vd):
        if d > 0:
            inputs += ["-i", str(tmp / f"n{i}.mp3")]
            k = len(labs)
            ms = int(starts[i] * 1000)
            filt.append(f"[{k}:a]aresample=22050,aformat=channel_layouts=mono,adelay={ms}|{ms}[a{k}]")
            labs.append(f"[a{k}]")
    narr = tmp / "narasi.wav"
    if labs:
        subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", *inputs, "-filter_complex",
                        ";".join(filt) + ";" + "".join(labs) + f"amix=inputs={len(labs)}:normalize=0,apad,atrim=0:{total:.2f}[o]",
                        "-map", "[o]", "-ar", "22050", "-ac", "1", str(narr)], check=True)
        cl = tmp / "narasi_cicilia.wav"
        state.work("desain", "Mengubah ke suara khas Cicilia...")
        if suara.kloning(cfg, narr, cl) and suara.duration(cl) > 1:
            narr = cl
            print("Suara Cicilia (kloning) dipakai")

    # 2) video dasar dari klip Cicilia
    state.work("desain", "Menyusun klip Cicilia & teks berjalan...")
    base = tmp / "base.mp4"
    base_video(scenes, total, end_start, base, seed)

    # 3) overlay teks per frame (dipipa ke ffmpeg)
    harga_txt, ket_txt = "", ""
    if product:
        pk = harga.paket_aktif(cfg, state)
        ids = [i for i in product.get("paket", []) if i in pk]
        if ids:
            p0 = min((pk[i] for i in ids), key=lambda x: x["harga"])
            harga_txt = harga.rp(p0["harga"])
            ket_txt = "sekali bayar" + (f" • {p0['ket'].split(' + ')[0]}" if p0.get("ket") else "")
        else:
            m = re.search(r"Rp[\d.]+", product.get("price", ""))
            harga_txt = m.group(0) if m else ""
            ket_txt = "sekali bayar"
    views = []  # (t_mulai, t_akhir, words, ekor_warna, y)
    for i, x in enumerate(scenes):
        toks = tokens(x["say"])
        tms = timing(toks, x["t0"] + 0.05, x["t0"] + x["speech"] - 0.1)
        x["chips_y0"] = 1215
        cy = 1050 if x.get("chips") else 1330
        vs = chunks(toks, tms)
        for j, v in enumerate(vs):
            t_a = v[0][2][0]
            t_b = vs[j + 1][0][2][0] if j + 1 < len(vs) else x["t0"] + x["dur"] - 0.02
            ekor = (RED, WHITE) if (i == 0 or "?" in " ".join(w for w, _, _ in v)) else (GOLD, NAVY)
            views.append((t_a, t_b, v, ekor, cy))
    bdg = badge(cfg)
    chip_cache = {}
    cache = {}

    def frame_at(tt):
        if tt >= end_start:
            te = tt - end_start
            key = ("end", round(min(te, 2.0) * 30) if te < 2 else 60 + int((te * 10) % 13))
            if key not in cache:
                cache[key] = end_card(cfg, sc, product, harga_txt, ket_txt, te, promo).tobytes()
            return cache[key]
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        im.alpha_composite(bdg, (0, 0))
        for (a, b, v, ekor, cy) in views:
            if a <= tt < b:
                shown = sum(1 for _, _, tm in v if tm[0] <= tt) or 1
                ck = (id(v), shown)
                if ck not in cache:
                    cache[ck] = caption_img(v, shown, ekor)
                ci = cache[ck]
                age = tt - a
                s = 1.18 - 0.18 * ease(age / 0.16)
                paste_scaled(im, ci, W / 2, cy + ci.height / 2, s, ease(age / 0.1))
        for x in scenes:
            if x.get("chips") and x["t0"] <= tt < x["t0"] + x["dur"]:
                n = len(x["chips"][:4])
                for k, c in enumerate(x["chips"][:4]):
                    tk = x["t0"] + 0.35 + k * max(0.35, (x["speech"] - 0.6) / n)
                    if tt >= tk:
                        if c not in chip_cache:
                            chip_cache[c] = chip_img(c)
                        a = ease((tt - tk) / 0.22)
                        paste_scaled(im, chip_cache[c], W / 2, x["chips_y0"] + k * 92 + 40 * (1 - a), 1.0, a)
        return im.tobytes()

    video = out_dir / "reels.mp4"
    mood_music = sc.get("mood", "semangat")
    music = suara.music_track(cfg, total, "semangat" if promo else mood_music, seed, tmp)
    vol = s_cfg.get("volume_musik", 0.16)
    ff = subprocess.Popen([_ffmpeg(), "-y", "-loglevel", "error", "-i", str(base),
                           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "pipe:0",
                           "-i", str(narr), "-stream_loop", "-1", "-i", str(music),
                           "-filter_complex",
                           f"[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v];"
                           f"[2:a]aresample=44100,aformat=channel_layouts=stereo,volume=1.7[n];"
                           f"[3:a]aresample=44100,aformat=channel_layouts=stereo,atrim=0:{total:.2f},lowpass=f=4200,"
                           f"afade=t=out:st={max(0, total - 1.5):.2f}:d=1.5,volume={vol}[m];"
                           f"[n][m]amix=inputs=2:normalize=0:duration=longest,atrim=0:{total:.2f},alimiter=limit=0.95[a]",
                           "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast",
                           "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(video)],
                          stdin=subprocess.PIPE)
    nfr = int(total * FPS)
    for fi in range(nfr):
        ff.stdin.write(frame_at(fi / FPS))
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg gagal merakit video kinetik")

    # 4) sampul: judul di atas, Cicilia di bawah (tidak menimpa wajah/badan)
    from . import reels
    t_theme = D.THEMES[rnd.choice(["navy", "merah", "ungu"])]
    try:
        st = D.choose_style(state, draft_id, "asn", "reels", {"hook": sc.get("hook", ""), "mood": sc.get("mood")})
        cov = reels.frame_hook(cfg, t_theme, st, {"hook": sc.get("hook", "")})
    except Exception:
        cov = end_card(cfg, sc, product, harga_txt, ket_txt, 3, promo)
    cover = out_dir / "cover.jpg"
    cov.convert("RGB").save(cover, quality=90)
    state.done("desain", f"Video kinetik {total:.0f} detik siap")
    return str(video.relative_to(ROOT)), str(cover.relative_to(ROOT))
