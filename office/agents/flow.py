"""Video semi-otomatis lewat Google Flow (Veo) milik Bos.

Alur:
1. Tiap pagi (slot pertama) — atau perintah /flow — kantor menulis BRIEF video: 2 prompt Veo siap tempel
   (Cicilia berbicara bahasa Indonesia, lokasi & cerita berbeda tiap hari) + 2 foto referensi Cicilia.
2. Bos membuat klipnya di Flow (Ingredients to Video, 9:16), unduh, lalu kirim/balas video ke bot.
3. Kantor menggabungkan klip, menambah subtitle, lencana merek & kartu penutup (produk/harga atau follow),
   lalu menerbitkan di jam slot video (atau langsung bila jamnya sudah lewat).
"""
import html
import random
import re
import subprocess
import tempfile
from pathlib import Path

import requests
from PIL import Image, ImageDraw

from ..core import ROOT, PUBLIC, now_wit
from .. import llm, telegram
from . import suara, videokinetik as VK
from .tiktok import _ffmpeg

W, H, FPS = 1080, 1920, 30
REF = [ROOT / "assets" / "influencer" / "referensi_wajah.jpg", ROOT / "assets" / "influencer" / "09_Ceria_Tangan_Terbuka.png"]

KARAKTER = ("Cicilia, a friendly Indonesian woman in her mid-20s, fair warm skin, long wavy dark-brown hair with soft highlights, "
            "bright smile, wearing a neat khaki Indonesian civil-servant uniform (PDH ASN) fully buttoned and modest, black belt, "
            "red-and-black 'ASN Go Digital' patch on the right sleeve, small name tag 'CICILIA I. H.', gold wristwatch. "
            "Same face and outfit as the reference images.")
GAYA = ("Vertical 9:16, photorealistic, natural light, handheld smartphone vlog feel with gentle camera movement, "
        "shallow depth of field. She speaks warmly in Bahasa Indonesia (Indonesian accent), lip-synced, clear voice, "
        "light ambient sound only, no background music. No subtitles, no captions, no on-screen text, no logos.")

SCHEMA = """
Balas HANYA JSON:
{
 "judul": "judul video maks 8 kata (untuk sampul & caption)",
 "konsep": "1 kalimat ide video",
 "lokasi": "lokasi syuting singkat (bahasa Indonesia)",
 "klip": [
   {"adegan": "deskripsi adegan dalam BAHASA INGGRIS: lokasi spesifik, aksi Cicilia, gerak kamera (1-2 kalimat)",
    "dialog": "ucapan Cicilia bahasa Indonesia, 12-18 kata (muat diucapkan dalam 8 detik). Tandai 1-3 kata penting dengan [kurung siku]",
    "teks": "teks layar singkat maks 5 kata"}
 ],
 "caption": "caption IG/TikTok 2-4 paragraf pendek, ajakan di akhir",
 "hashtags": ["#..."]
}
Aturan: tepat {n} klip yang bersambung jadi satu cerita (klip 1 = hook kuat dalam 2 detik pertama).
Lokasi & situasi HARUS berbeda dari daftar 'sudah dipakai'. Pilih situasi nyata ASN/perangkat desa di Indonesia
(kantor dinas, balai kampung, posyandu, musyawarah desa, rapat koordinasi, pasar, sawah, dermaga, perjalanan dinas, dsb).
Dialog natural, hangat, tidak kaku, tanpa emoji. Jangan mengarang fitur/harga di luar brief."""


def _cfg(cfg):
    f = cfg.get("flow", {})
    return {"klip": int(f.get("klip", 2)), "model": f.get("model", "Veo 3.1 - Lite"), "subtitle": f.get("subtitle", True),
            "karakter": f.get("karakter", KARAKTER), "gaya": f.get("gaya", GAYA), "kredit": int(f.get("kredit_per_klip", 10))}


def prompt_veo(fc, k):
    return (f"{fc['karakter']} {k['adegan'].strip()} She says in Indonesian: \"{VK.bersih(k['dialog']).strip()}\" "
            f"{fc['gaya']}")


def brief(cfg, state, slot_jam=None, topic=None, promo=None, pillar_id=None):
    """Buat brief video Flow + kirim ke Telegram. Kembalikan id draft."""
    from . import naskah, cuan
    fc = _cfg(cfg)
    pillar, auto_topic = naskah.pick_topic(cfg, pillar_id)
    topic = topic or auto_topic
    if promo is None:
        promo = now_wit().date().toordinal() % 2 == 0  # selang-seling: hari genap promosi produk
    product = cuan.pick_product(cfg, state, pillar["id"], force=promo, product_id=("naskah" if promo else None))
    used = state.d.setdefault("flow_lokasi", [])
    state.work("naskah", f"Menulis brief video Flow: {topic[:45]}")
    if promo and product:
        isi = (f"Video PROMOSI soft-selling. Produk: {product['name']} ({product['price']}). Fakta produk (HANYA ini): "
               f"{product.get('pitch', '')}\nAlur: situasi masalah nyata → Cicilia menunjukkan solusinya di laptop/HP → manfaat → ajak cek link di bio.")
    else:
        isi = (f"Video EDUKASI. Pilar: {pillar['name']}. Topik: {topic}.\nAlur: hook masalah → 1-2 tips inti yang bisa langsung dipraktikkan → ajak simpan & follow.")
    sc = llm.ask(isi + f"\nSudah dipakai (hindari): {', '.join(used[-15:]) or '-'}\n" + SCHEMA.replace("{n}", str(fc["klip"])),
                 naskah._system(cfg), as_json=True)
    klip = [k for k in sc.get("klip", []) if k.get("dialog") and k.get("adegan")][:fc["klip"]]
    if not klip:
        raise RuntimeError("Brief video kosong dari AI")
    used.append(sc.get("lokasi", "")[:40])
    state.d["flow_lokasi"] = used[-40:]
    did = "F" + state.new_draft_id()
    for k in klip:
        k["prompt"] = prompt_veo(fc, k)
    jam = slot_jam or now_wit().strftime("%H:%M")
    state.d["drafts"][did] = {
        "id": did, "type": "flow", "status": "menunggu_video", "created": now_wit().isoformat(timespec="minutes"),
        "pillar": pillar["name"], "topic": topic, "format": "flow_promo" if promo else "flow_edukasi",
        "product": product and product["id"], "promo": bool(promo), "slot_jam": jam,
        "content": {"hook": sc.get("judul", ""), "caption": sc.get("caption", ""), "hashtags": sc.get("hashtags", []),
                    "konsep": sc.get("konsep", ""), "lokasi": sc.get("lokasi", ""), "klip": klip,
                    "_qc": {"issues": [], "risk": "rendah"}},
        "images": [], "klip_masuk": [],
    }
    state.d["stats"]["drafts"] += 1
    kirim_brief(cfg, state, did)
    state.done("naskah", f"Brief video Flow #{did} dikirim ke Bos")
    return did


def kirim_brief(cfg, state, did):
    e = html.escape
    d = state.d["drafts"][did]
    c = d["content"]
    fc = _cfg(cfg)
    n = len(c["klip"])
    try:
        telegram.send_album([p for p in REF if p.exists()], "🧍‍♀️ Foto referensi Cicilia — unggah sebagai Ingredients di Flow (cukup sekali, simpan sebagai karakter)")
    except Exception as ex:
        print("foto referensi gagal:", ex)
    head = (f"🎬 <b>Brief Video Flow #{did}</b> — {'PROMOSI' if d['promo'] else 'EDUKASI'} • tayang ±{d['slot_jam']} WIT\n"
            f"<b>{e(c['hook'])}</b>\n{e(c.get('konsep', ''))}\n📍 {e(c.get('lokasi', ''))}\n\n"
            f"<b>Cara buat di Flow</b> (±{n * 2} menit, ±{n * fc['kredit']} kredit):\n"
            "1. Buka labs.google/flow → proyek baru → <b>Ingredients to Video</b> (atau karakter Cicilia yang sudah disimpan)\n"
            f"2. Model <b>{e(fc['model'])}</b>, rasio <b>9:16</b>, jumlah output <b>1</b>\n"
            "3. Tempel Prompt 1 → Generate. Ulangi untuk prompt berikutnya\n"
            f"4. Unduh tiap klip, lalu <b>balas pesan ini</b> dengan videonya (boleh {n} klip terpisah atau 1 video gabungan)\n"
            "Kantor yang menambah subtitle, logo, kartu penutup & caption, lalu memposting sesuai jadwal.")
    telegram.send(head)
    for i, k in enumerate(c["klip"], 1):
        telegram.send(f"🎞 <b>Prompt {i}/{n}</b> #{did} (tekan untuk menyalin)\n<code>{e(k['prompt'])}</code>\n\n"
                      f"🗣 Dialog: <i>{e(VK.bersih(k['dialog']))}</i>")


# ------------------------------------------------------------------ menerima klip dari Bos
def tunggu(state):
    return sorted([d for d in state.d["drafts"].values() if d.get("type") == "flow" and d.get("status") == "menunggu_video"],
                  key=lambda x: x["created"])


def cocokkan(state, msg):
    teks = " ".join([msg.get("caption") or "", (msg.get("reply_to_message") or {}).get("text") or "",
                     (msg.get("reply_to_message") or {}).get("caption") or ""])
    m = re.search(r"#(F\d+)", teks)
    if m and m.group(1) in state.d["drafts"]:
        return state.d["drafts"][m.group(1)]
    t = tunggu(state)
    return t[0] if t else None


def terima_video(cfg, state, msg):
    """Dipanggil saat Bos mengirim video. Simpan file_id; rakit bila klip sudah lengkap."""
    v = msg.get("video") or msg.get("document") or {}
    if msg.get("document") and not str(v.get("mime_type", "")).startswith("video"):
        telegram.send("📎 File diterima, tapi bukan video. Kirim klip dari Flow sebagai video (mp4).")
        return
    d = cocokkan(state, msg)
    if not d:
        telegram.send("🎬 Video diterima, tapi belum ada brief Flow yang menunggu. Buat brief dulu dengan /flow")
        return
    if v.get("file_size", 0) > 20 * 1024 * 1024:
        telegram.send("⚠️ Video lebih dari 20 MB — batas unduhan bot Telegram. Kirim ulang sebagai <b>video</b> (bukan file) "
                      "supaya Telegram mengompresnya, atau unduh dari Flow di 720p.")
        return
    d.setdefault("klip_masuk", []).append({"file_id": v["file_id"], "durasi": v.get("duration", 0)})
    n = len(d["content"]["klip"])
    total = sum(k.get("durasi", 0) for k in d["klip_masuk"])
    lengkap = len(d["klip_masuk"]) >= n or total >= n * 8 * 0.8 or "/jadi" in (msg.get("caption") or "")
    if not lengkap:
        telegram.send(f"✅ Klip {len(d['klip_masuk'])}/{n} untuk #{d['id']} diterima. Kirim klip berikutnya "
                      f"(atau ketik <code>/jadi {d['id']}</code> bila sudah cukup).")
        return
    rakit(cfg, state, d["id"])


def unduh(file_id, out):
    r = telegram.raw("getFile", {"file_id": file_id})
    if not r.get("ok"):
        raise RuntimeError(f"getFile gagal: {r.get('description')}")
    url = f"https://api.telegram.org/file/bot{telegram.bot_token()}/{r['result']['file_path']}"
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(out, "wb") as f:
            for ch in resp.iter_content(1 << 16):
                f.write(ch)
    return out


def _small_badge(cfg):
    im = Image.new("RGBA", (W, 160), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([W - 360, 40, W - 30, 118], 39, fill=(11, 31, 58, 215))
    d.rounded_rectangle([W - 350, 50, W - 292, 108], 14, fill=VK.RED + (255,))
    d.text((W - 321, 79), "AG", font=VK.font("int_k", 28), fill=VK.WHITE, anchor="mm")
    d.text((W - 278, 79), cfg["brand"]["handle"], font=VK.font("pop_b", 26), fill=VK.WHITE, anchor="lm")
    return im


def rakit(cfg, state, did):
    from .. import harga
    d = state.d["drafts"][did]
    c = d["content"]
    fc = _cfg(cfg)
    telegram.send(f"🛠 Kaka Elisa merakit video #{did} (subtitle, logo, kartu penutup)... ±2 menit")
    state.work("desain", f"Merakit video Flow #{did}")
    tmp = Path(tempfile.mkdtemp())
    clips = []
    for i, k in enumerate(d["klip_masuk"]):
        src = unduh(k["file_id"], tmp / f"in{i}.mp4")
        norm = tmp / f"c{i}.mp4"
        has_a = "Audio:" in subprocess.run([_ffmpeg(), "-i", str(src)], capture_output=True, text=True).stderr
        cmd = [_ffmpeg(), "-y", "-loglevel", "error", "-i", str(src)]
        if not has_a:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        cmd += ["-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,format=yuv420p",
                "-map", "0:v", "-map", "0:a" if has_a else "1:a", "-shortest", "-ar", "44100", "-ac", "2",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(norm)]
        subprocess.run(cmd, check=True)
        clips.append((norm, suara.duration(norm)))
    end_start = sum(x[1] for x in clips)
    tail = 3.2
    total = end_start + tail

    # dasar: klip bersambung + latar kartu penutup, audio Veo + musik penutup
    base = tmp / "base.mp4"
    cmd = [_ffmpeg(), "-y", "-loglevel", "error"]
    for p, _ in clips:
        cmd += ["-i", str(p)]
    n = len(clips)
    cmd += ["-f", "lavfi", "-i", f"color=c=0x0B1F3A:s={W}x{H}:r={FPS}:d={tail}", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={tail}"]
    cc = "".join(f"[{i}:v][{i}:a]" for i in range(n)) + f"[{n}:v][{n + 1}:a]"
    cmd += ["-filter_complex", f"{cc}concat=n={n + 1}:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(base)]
    subprocess.run(cmd, check=True)

    # subtitle (dialog brief, dibagi rata sepanjang klip) + teks layar + lencana + kartu penutup
    views = []
    t = 0.0
    for (p, du), k in zip(clips, c["klip"] + [c["klip"][-1]] * max(0, n - len(c["klip"]))):
        if fc["subtitle"] and len(clips) == len(c["klip"]):
            toks = VK.tokens(k["dialog"])
            tms = VK.timing(toks, t + 0.4, t + du - 0.5)
            vs = VK.chunks(toks, tms)
            for j, v in enumerate(vs):
                a = v[0][2][0]
                b = vs[j + 1][0][2][0] if j + 1 < len(vs) else t + du - 0.05
                views.append((a, b, v, (VK.GOLD, VK.NAVY), 1380))
        t += du
    product = next((x for x in cfg.get("products", []) if x["id"] == d.get("product")), None)
    harga_txt, ket_txt = "", ""
    if product:
        pk = harga.paket_aktif(cfg, state)
        ids = [i for i in product.get("paket", []) if i in pk]
        if ids:
            p0 = min((pk[i] for i in ids), key=lambda x: x["harga"])
            harga_txt = harga.rp(p0["harga"])
            ket_txt = "sekali bayar" + (f" • {p0['ket'].split(' + ')[0]}" if p0.get("ket") else "")
    sc_end = {"penutup_tag": "SURAT DINAS 1 MENIT" if d["promo"] else "FOLLOW BIAR NGGAK KETINGGALAN"}
    bdg = _small_badge(cfg)
    cache = {}

    def frame_at(tt):
        if tt >= end_start:
            te = tt - end_start
            key = ("end", round(min(te, 2.0) * 30) if te < 2 else 60 + int((te * 10) % 13))
            if key not in cache:
                cache[key] = VK.end_card(cfg, sc_end, product, harga_txt, ket_txt, te, d["promo"]).tobytes()
            return cache[key]
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        im.alpha_composite(bdg, (0, 0))
        for (a, b, v, ekor, cy) in views:
            if a <= tt < b:
                shown = sum(1 for _, _, tm in v if tm[0] <= tt) or 1
                ck = (id(v), shown)
                if ck not in cache:
                    cache[ck] = VK.caption_img(v, shown, ekor)
                ci = cache[ck]
                age = tt - a
                VK.paste_scaled(im, ci, W / 2, cy + ci.height / 2, 1.12 - 0.12 * VK.ease(age / 0.14), VK.ease(age / 0.1))
        return im.tobytes()

    out_dir = PUBLIC / did
    out_dir.mkdir(parents=True, exist_ok=True)
    video = out_dir / "reels.mp4"
    music = suara.music_track(cfg, tail + 0.5, "semangat", hash(did) % 1000, tmp)
    ff = subprocess.Popen([_ffmpeg(), "-y", "-loglevel", "error", "-i", str(base),
                           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "pipe:0",
                           "-i", str(music), "-filter_complex",
                           f"[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v];"
                           f"[2:a]aresample=44100,aformat=channel_layouts=stereo,atrim=0:{tail:.2f},afade=t=in:d=0.3,"
                           f"afade=t=out:st={tail - 1:.2f}:d=1,volume=0.35,adelay={int(end_start * 1000)}|{int(end_start * 1000)}[m];"
                           f"[0:a][m]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[a]",
                           "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast",
                           "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(video)],
                          stdin=subprocess.PIPE)
    for fi in range(int(total * FPS)):
        ff.stdin.write(frame_at(fi / FPS))
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg gagal merakit video Flow")
    cover = out_dir / "cover.jpg"
    subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-ss", "1.2", "-i", str(clips[0][0]), "-frames:v", "1", "-q:v", "3", str(cover)], check=True)

    # jadi draft Reels biasa → terbit di jam slot (atau segera bila jam sudah lewat)
    from . import cuan
    if not d["promo"] and product:
        c.update(cuan.add_soft_cta(cfg, {"caption": c["caption"]}, product))
    elif product and cfg.get("lynk_url") and cfg["lynk_url"] not in c["caption"]:
        c["caption"] += f"\n\n👉 {product['name']} — {product['price']}. Link di bio: {cfg['lynk_url']}"
    d.update({"type": "reels", "video": str(video.relative_to(ROOT)), "images": [str(cover.relative_to(ROOT))]})
    jam = d.get("slot_jam", "00:00")
    when = now_wit().strftime("%Y-%m-%dT") + jam
    d["scheduled_at"] = max(when, now_wit().isoformat(timespec="minutes")[:16])
    auto = cfg.get("slot_autopublish", True)
    d["status"] = "approved" if auto else "draft"
    state.done("desain", f"Video Flow #{did} siap ({total:.0f} detik)")
    telegram.send_video(video, f"🎬 Video #{did} siap ({total:.0f} dtk)")
    nanti = d["scheduled_at"] > now_wit().isoformat(timespec="minutes")[:16]
    telegram.send((f"✅ Terjadwal terbit <b>{jam} WIT</b>." if nanti else "🚀 Diterbitkan sekarang.") if auto else
                  "⏸ Menunggu persetujuan Bos.",
                  [[("🚀 Terbit sekarang", f"now:{did}"), ("🗑 Tolak", f"no:{did}")]])
