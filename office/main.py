"""Bapa Yohanis — manajer kantor. Menjalankan rutinitas dan menerima perintah Bos lewat Telegram.

Pemakaian (dipanggil oleh GitHub Actions):
    python -m office.main daily    # buat draft konten hari ini
    python -m office.main poll     # baca perintah Telegram + terbitkan draft yang jatuh tempo
    python -m office.main weekly   # laporan performa mingguan
    python -m office.main event    # proses update Telegram dari webhook (mode instan, opsional)
    python -m office.main demo     # uji desain tanpa API apa pun
    python -m office.main cek      # cek kesehatan: token, chat ID, webhook, Gemini, Meta
"""
import datetime as dt
import html
import json
import os
import sys

from . import telegram, jadwal, harga
from .core import State, load_config, now_wit, WIT, AGENTS
from .agents import riset, naskah, desain, humas, cuan, analis, foto, tiktok, reels, berita

HELP = """🏢 <b>Kantor Virtual ASN GO Digitals</b>
Perintah untuk Bos:

/buat [topik] — buat carousel baru (topik opsional)
/reels [topik] — buat video Reels baru (suara Cicilia)
/reels promo — video promosi produk (gaya promo kinetik)
/berita [topik] — carousel berita terkini dari media tepercaya
/buat_promo [id_produk] — carousel soft-selling produk
/ide — 10 ide konten
/antrian — daftar draft
/lihat [id] — pratinjau ulang draft
/setuju [id] — setujui & langsung terbit
/terbit [id] — terbitkan sekarang
/revisi [id] [catatan] — tulis ulang dengan catatan
/tolak [id] — buang draft
/promo [id_produk] — copy promosi WA/Story
/tiktok [id] — kirim ulang paket TikTok (video + caption)
/produk — daftar produk lynk.id
/harga — lihat & ubah harga paket (CTA ikut berubah)
/sudah [id] — tandai paket manual sudah diposting
/laporan — laporan performa
/jadwal — jadwal posting hari ini (/jadwal besok)
/status — apa yang sedang dikerjakan karyawan
/otomatis on|off — terbit tanpa persetujuan
/bantuan — menu ini"""

FMT_LABEL = {
    "carousel_tutorial": "Tutorial", "carousel_listicle": "Listicle", "carousel_prompt": "Contekan Prompt",
    "carousel_mitos": "Mitos vs Fakta", "carousel_promo": "Soft-selling",
}


VIA_WEBHOOK = False  # True bila perintah datang lewat Cloudflare Worker (Worker sudah membalas "diterima")


def ack(text):
    """Balasan cepat 'perintah diterima' — dilewati bila Worker sudah mengirimnya."""
    if not VIA_WEBHOOK:
        telegram.send(text)


def esc(s):
    return html.escape(str(s or ""))


def next_slot(cfg):
    now = now_wit()
    slot = now.replace(hour=int(cfg.get("post_hour_wit", 19)), minute=0, second=0, microsecond=0)
    if slot <= now + dt.timedelta(minutes=20):
        slot += dt.timedelta(days=1)
    return slot.isoformat(timespec="minutes")


# ------------------------------------------------------------------ produksi
def create_draft(cfg, state, topic=None, pillar_id=None, fmt=None, product_id=None, notes=None, base=None):
    state.work("kepala", "Membagi tugas produksi konten")
    plan = cfg["weekly_plan"][now_wit().weekday()]
    if not fmt:
        fmt = plan["format"]
        if topic and fmt == "carousel_promo":  # topik dari Bos → konten edukasi, bukan jualan
            fmt = "carousel_tutorial"
    pillar, auto_topic = naskah.pick_topic(cfg, pillar_id or plan["pillar"])
    topic = topic or auto_topic

    promo = fmt == "carousel_promo" or product_id
    product = cuan.pick_product(cfg, state, pillar["id"], force=bool(promo), product_id=product_id)
    news = riset.headlines(cfg, state) if not base else None

    content = naskah.write(cfg, state, pillar, topic, fmt, news=news, product=product if promo else None, notes=notes,
                           avoid=state.d.get("recent_hooks", []))
    content = naskah.verify(cfg, state, content)
    if not promo:
        content = cuan.add_soft_cta(cfg, content, product)

    disclosure = cfg.get("influencer", {}).get("disclosure")
    if disclosure and disclosure not in content.get("caption", ""):
        content["caption"] = content.get("caption", "") + "\n\n" + disclosure

    did = base or state.new_draft_id()
    scene = foto.generate_cover(cfg, state, content)
    images = desain.render(cfg, state, did, content, pillar["name"], fmt, product, scene=scene, pillar_id=pillar["id"])
    remember_hook(state, content.get("hook", ""))
    state.d["drafts"][did] = {
        "id": did, "status": "draft", "created": now_wit().isoformat(timespec="minutes"),
        "pillar": pillar["name"], "topic": topic, "format": fmt, "product": product and product["id"],
        "content": content, "images": images, "scheduled_at": next_slot(cfg),
    }
    state.d["stats"]["drafts"] += 1
    if state.auto_publish(cfg):
        state.d["drafts"][did]["status"] = "approved"
    preview(cfg, state, did)
    state.done("kepala", f"Draft #{did} dikirim ke Bos")
    return did


def remember_hook(state, hook):
    rh = state.d.setdefault("recent_hooks", [])
    if hook:
        rh.append(hook)
    state.d["recent_hooks"] = rh[-40:]


def create_reels(cfg, state, topic=None, pillar_id=None, notes=None, base=None, promo=False):
    from .agents import videokinetik
    state.work("kepala", "Membagi tugas produksi Reels" + (" promosi" if promo else ""))
    pillar, auto_topic = naskah.pick_topic(cfg, pillar_id)
    topic = topic or auto_topic
    product = cuan.pick_product(cfg, state, pillar["id"], force=promo, product_id=("naskah" if promo else None))
    if cfg.get("video", {}).get("gaya", "kinetik") == "kinetik" and list(videokinetik.CLIP_DIR.glob("cicilia_*.mp4")):
        sc = videokinetik.write_script(cfg, state, pillar, topic + (f" (catatan Bos: {notes})" if notes else ""),
                                       product=product, promo=promo, avoid=state.d.get("recent_hooks", []))
        content = {"hook": sc.get("hook", ""), "caption": sc.get("caption", ""), "hashtags": sc.get("hashtags", []),
                   "mood": sc.get("mood", "semangat"), "narasi": [videokinetik.bersih(x["say"]) for x in sc["scenes"]],
                   "_qc": {"issues": [], "risk": "rendah"}}
        if not promo:
            content = cuan.add_soft_cta(cfg, content, product)
        elif cfg.get("lynk_url") and cfg["lynk_url"] not in content["caption"]:
            content["caption"] += f"\n\n👉 {product['name']} — {product['price']}. Link di bio: {cfg['lynk_url']}"
        did = base or state.new_draft_id()
        video, cover = videokinetik.render(cfg, state, did, sc, product, promo=promo, seed=hash(did) % 10000)
        remember_hook(state, content["hook"])
        state.d["drafts"][did] = {
            "id": did, "type": "reels", "status": "draft", "created": now_wit().isoformat(timespec="minutes"),
            "pillar": pillar["name"], "topic": topic, "format": "reels_promo" if promo else "reels_kinetik",
            "product": product and product["id"], "content": content, "images": [cover], "video": video,
            "scheduled_at": now_wit().isoformat(timespec="minutes"), "promo": promo,
        }
        state.d["stats"]["drafts"] += 1
        preview(cfg, state, did)
        state.done("kepala", f"Video #{did} dikirim ke Bos")
        return did
    news = riset.headlines(cfg, state) if not base else None
    sc = reels.write_script(cfg, state, pillar, topic + (f" (catatan Bos: {notes})" if notes else ""), news=news,
                            product=product, avoid=state.d.get("recent_hooks", []))
    content = {"hook": sc.get("hook", ""), "caption": sc.get("caption", ""), "hashtags": sc.get("hashtags", []),
               "beats": sc.get("beats", []), "_qc": {"issues": [], "risk": "rendah"}}
    content = cuan.add_soft_cta(cfg, content, product)
    disclosure = cfg.get("influencer", {}).get("disclosure")
    if disclosure:
        content["caption"] += "\n\n" + disclosure
    did = base or state.new_draft_id()
    video, cover = reels.render(cfg, state, did, sc, pillar["name"], pillar["id"], product)
    remember_hook(state, content["hook"])
    state.d["drafts"][did] = {
        "id": did, "type": "reels", "status": "draft", "created": now_wit().isoformat(timespec="minutes"),
        "pillar": pillar["name"], "topic": topic, "format": "reels", "product": product and product["id"],
        "content": content, "images": [cover], "video": video, "scheduled_at": now_wit().isoformat(timespec="minutes"),
    }
    state.d["stats"]["drafts"] += 1
    preview(cfg, state, did)
    state.done("kepala", f"Reels #{did} dikirim ke Bos")
    return did


BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def create_news(cfg, state, pillar_id=None, topic=None):
    """Carousel BERITA TERKINI. Kembalikan id draft, atau None bila tidak ada berita baru."""
    state.work("kepala", "Meminta tim memantau berita terkini")
    arts, photos = berita.gather(cfg, state, pillar_id, topic)
    if not arts:
        return None
    state.work("naskah", f"Merangkum berita dari {len(arts)} sumber...")
    data = berita.summarize(cfg, state, arts, photos)
    state.done("naskah", f"Rangkuman: \"{data.get('judul', '')}\"")
    data = berita.verify(cfg, state, data, arts)
    srcs = list(dict.fromkeys(a["source"] for a in arts))
    pub = arts[0].get("published") or now_wit().isoformat()
    try:
        dt_ = datetime_fromiso(pub)
        date_text = f"{dt_.day} {BULAN[dt_.month - 1]} {dt_.year}"
    except Exception:
        date_text = now_wit().strftime("%d/%m/%Y")
    did = state.new_draft_id()
    images = desain.render_news(cfg, state, did, data, photos, " • ".join(srcs[:3]), date_text)
    tags = " ".join(data.get("hashtags", [])[:10])
    cap = (f"{data.get('judul', '')}\n\n{data.get('caption', '')}\n\n"
           + (f"💡 Artinya bagi kita: {data['dampak']}\n\n" if data.get("dampak") else "")
           + "📰 Sumber:\n" + "\n".join(f"• {a['source']}: {a['url']}" for a in arts)
           + ("\n📷 Foto: " + ", ".join(dict.fromkeys(p["source"] for p in photos)) if photos else "")
           + "\n\nDirangkum ulang oleh tim ASN GO Digitals. Baca berita lengkap di sumber aslinya.")
    narasi = data.get("_narasi") or [data.get("judul", "")]
    content = {"hook": data.get("judul", ""), "caption": cap, "hashtags": data.get("hashtags", []), "_qc": data.get("_qc", {}),
               "narasi": narasi, "mood": "tenang"}
    remember_hook(state, content["hook"])
    state.d["drafts"][did] = {
        "id": did, "type": "berita", "status": "draft", "created": now_wit().isoformat(timespec="minutes"),
        "pillar": desain.PILAR_LABEL.get(data.get("pilar"), "Berita"), "topic": arts[0]["title"], "format": "berita",
        "content": content, "images": images, "sources": [a["url"] for a in arts], "scheduled_at": now_wit().isoformat(timespec="minutes"),
    }
    state.d["stats"]["drafts"] += 1
    preview(cfg, state, did)
    state.done("kepala", f"Berita #{did} dikirim ke Bos")
    return did


def datetime_fromiso(s_):
    return dt.datetime.fromisoformat(s_.replace("Z", "+00:00")).astimezone(WIT)


def slot_plan(cfg, idx):
    """Rotasi pilar & format per slot agar tiap hari berbeda."""
    return jadwal.plan(cfg, idx, now_wit().date())


def run_slot(cfg, state, idx):
    slot, pillar_id, fmt = slot_plan(cfg, idx)
    if jadwal.sudah_jalan(state, idx):
        print(f"Slot {idx} ({slot['time']}) hari ini sudah dikerjakan — dilewati.")
        return
    state.work("kepala", f"Jadwal {slot['time']} WIT: {slot['type']} {pillar_id}")
    jadwal.log_slot(state, idx)
    state.save()
    try:
        if slot["type"] == "reels":
            did = create_reels(cfg, state, pillar_id=pillar_id, promo=bool(slot.get("promo")))
        elif slot["type"] == "berita":
            did = create_news(cfg, state, pillar_id=None)
            if not did:  # tidak ada berita baru → carousel edukasi biasa
                did = create_draft(cfg, state, pillar_id=pillar_id, fmt="carousel_listicle")
        else:
            did = create_draft(cfg, state, pillar_id=pillar_id, fmt=fmt)
    except Exception:
        jadwal.log_slot(state, idx, status="gagal")
        raise
    jadwal.log_slot(state, idx, did)
    d = state.d["drafts"][did]
    risky = d["content"].get("_qc", {}).get("risk") == "tinggi"
    if cfg.get("slot_autopublish", True) and not risky:
        d["status"] = "approved"
        humas.publish(cfg, state, did)
    else:
        telegram.send(f"⏸ #{did} menunggu persetujuan Bos" + (" (QC: risiko tinggi)" if risky else "") +
                      ". Tekan ✅ Setujui untuk langsung terbit.")


def preview(cfg, state, did):
    d = state.d["drafts"].get(did)
    if not d:
        telegram.send(f"Draft #{esc(did)} tidak ditemukan.")
        return
    from .core import ROOT
    if d.get("type") == "reels":
        telegram.send_video(ROOT / d["video"], f"🎬 Reels #{did}")
    else:
        telegram.send_album([ROOT / p for p in d["images"]])
    qc = d["content"].get("_qc", {})
    issues = "\n".join(f"  • {esc(i)}" for i in qc.get("issues", [])[:5]) or "  • tidak ada"
    text = (f"📝 <b>Draft #{did}</b> — {esc(d['pillar'])} • {FMT_LABEL.get(d['format'], d['format'])}\n"
            f"Status: <b>{d['status']}</b>\n"
            f"🛡 QC risiko <b>{esc(qc.get('risk', '-'))}</b>:\n{issues}\n\n"
            f"<b>Caption:</b>\n{esc(humas.caption_of(d))[:2500]}")
    buttons = [[("✅ Setujui", f"ok:{did}"), ("🚀 Terbit sekarang", f"now:{did}")],
               [("🔁 Tulis ulang", f"redo:{did}"), ("🗑 Tolak", f"no:{did}")]]
    telegram.send(text, buttons)


# ------------------------------------------------------------------ perintah
def handle_command(cfg, state, text):
    parts = text.strip().split(maxsplit=2)
    cmd = parts[0].split("@")[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    rest = parts[2] if len(parts) > 2 else ""
    drafts = state.d["drafts"]

    if cmd in ("/start", "/bantuan", "/help"):
        telegram.send(HELP)
    elif cmd == "/buat":
        ack("👷 Siap Bos! Tim mulai produksi carousel... (± 1–2 menit)")
        create_draft(cfg, state, topic=(text.split(maxsplit=1)[1] if arg else None))
    elif cmd == "/reels":
        promo = arg.lower().startswith("promo")
        tp = text.split(maxsplit=1)[1] if arg else None
        if promo:
            tp = tp[5:].strip() or None
        ack("🎬 Tim membuat video" + (" promosi" if promo else "") + " dengan suara Cicilia... (± 3–5 menit)")
        create_reels(cfg, state, topic=tp, promo=promo)
    elif cmd == "/berita":
        ack("📰 Tim memantau berita terkini... (± 2–3 menit)")
        if not create_news(cfg, state, topic=(text.split(maxsplit=1)[1] if arg else None)):
            telegram.send("📰 Belum ada berita baru (24–48 jam terakhir) dari sumber tepercaya untuk topik itu. Coba topik lain, mis. /berita PPPK")
    elif cmd == "/buat_promo":
        ack("💰 Kaka Yance & tim menyiapkan konten soft-selling...")
        create_draft(cfg, state, fmt="carousel_promo", product_id=arg or None)
    elif cmd == "/ide":
        telegram.send("💡 <b>Ide konten dari Kaka Selfina:</b>\n\n" + esc(naskah.ideas(cfg, state)))
    elif cmd == "/antrian":
        rows = [f"#{k} • {v['status']} • {esc(v['content'].get('hook', ''))[:45]}"
                for k, v in sorted(drafts.items(), reverse=True)[:12]]
        telegram.send("🗂 <b>Antrian draft</b>\n" + ("\n".join(rows) or "kosong"))
    elif cmd == "/lihat":
        preview(cfg, state, arg)
    elif cmd in ("/setuju", "/terbit", "/tolak") and arg not in drafts:
        telegram.send(f"Draft #{esc(arg)} tidak ditemukan. Cek /antrian")
    elif cmd == "/setuju":
        drafts[arg]["status"] = "approved"
        drafts[arg]["scheduled_at"] = now_wit().isoformat(timespec="minutes")
        telegram.send(f"✅ #{arg} disetujui, sedang diterbitkan ke IG & FB...")
    elif cmd == "/terbit":
        drafts[arg]["status"] = "approved"
        drafts[arg]["scheduled_at"] = now_wit().isoformat(timespec="minutes")
        telegram.send(f"🚀 #{arg} sedang diterbitkan ke IG & FB...")
    elif cmd == "/tolak":
        drafts[arg]["status"] = "rejected"
        telegram.send(f"🗑 #{arg} dibuang.")
    elif cmd == "/revisi":
        if arg not in drafts:
            telegram.send("Format: /revisi [id] [catatan]")
        else:
            d = drafts[arg]
            ack(f"✍️ Kaka Selfina merevisi #{arg}...")
            p = next((x["id"] for x in cfg["pillars"] if x["name"] == d["pillar"]), None)
            if d.get("type") == "reels":
                create_reels(cfg, state, topic=d["topic"], pillar_id=p, notes=rest or "lebih menarik", base=arg, promo=bool(d.get("promo")))
                return
            create_draft(cfg, state, topic=d["topic"], pillar_id=p, fmt=d["format"],
                         product_id=d.get("product") if d["format"] == "carousel_promo" else None,
                         notes=rest or "buat lebih menarik dan lebih praktis", base=arg)
    elif cmd == "/tiktok":
        did = arg or next((k for k, v in sorted(drafts.items(), reverse=True) if v.get("status") in ("published", "approved", "draft")), "")
        tiktok.send_package(cfg, state, did)
    elif cmd == "/produk":
        rows = [f"• <code>{p['id']}</code> — {esc(p['name'])} ({p['price']})\n  {p['url']}" for p in cfg.get("products", [])]
        telegram.send("🛒 <b>Produk lynk.id</b>\n" + "\n".join(rows))
    elif cmd == "/sudah":
        if arg in drafts:
            drafts[arg]["status"] = "published"
            drafts[arg]["published_at"] = now_wit().isoformat(timespec="minutes")
            drafts[arg].setdefault("published", {})["manual"] = "diposting manual oleh Bos"
            state.d["stats"]["published"] += 1
            telegram.send(f"✅ #{arg} dicatat sudah terbit (manual). Terima kasih, Bos!")
        else:
            telegram.send("Format: <code>/sudah ID</code> — ID ada di pesan paket posting manual.")
    elif cmd == "/harga":
        a = arg.split()
        pk = harga.paket_aktif(cfg, state)
        if not a:
            telegram.send(harga.ringkas(cfg, state))
        elif a[0].lower() == "sync":
            ack("🔄 Kaka Yance mengecek harga di lynk.id...")
            ubah = harga.sync_lynk(cfg, state)
            info = state.d.get("harga", {}).get("sync", {}).get("hasil", "")
            msg = ("✅ Harga diperbarui dari lynk.id:\n" + "\n".join("• " + esc(u) for u in ubah)) if ubah else f"ℹ️ Tidak ada perubahan ({esc(info)})."
            if ubah is None or "tidak terbaca" in info:
                msg += "\nKalau lynk.id tidak bisa dibaca, ubah manual: <code>/harga pro 149000</code>"
            telegram.send(msg + "\n\n" + harga.ringkas(cfg, state))
        elif a[0].lower() == "reset":
            state.d.setdefault("harga", {})["paket"] = {}
            cfg = harga.apply(load_config(), state)
            telegram.send("↩️ Harga kembali ke config.\n\n" + harga.ringkas(cfg, state))
        elif a[0].lower() in pk and len(a) >= 2 and harga.parse_angka(a[1]):
            normal = None
            if len(a) >= 4 and a[2].lower() in ("normal", "coret"):
                normal = harga.parse_angka(a[3])
            set_to = harga.parse_angka(a[1])
            harga.set_harga(cfg, state, a[0].lower(), set_to, normal)
            telegram.send(f"✅ Harga paket <b>{esc(pk[a[0].lower()]['nama'])}</b> jadi <b>{harga.rp(set_to)}</b>"
                          + (f" (normal {harga.rp(normal)})" if normal else "")
                          + ". Mulai konten berikutnya, CTA & promo memakai harga ini.\n"
                          "⚠️ Jangan lupa samakan harga di lynk.id & landing page.\n\n" + harga.ringkas(cfg, state))
        else:
            telegram.send("Format: <code>/harga pro 149000</code> • paket: " + ", ".join(f"<code>{k}</code>" for k in pk)
                          + "\nAtau <code>/harga sync</code> untuk ambil dari lynk.id.")
    elif cmd == "/promo":
        prod = cuan.pick_product(cfg, state, None, product_id=arg) if arg else (cfg.get("products") or [None])[0]
        telegram.send(esc(cuan.promo_copy(cfg, state, prod)) if prod else "Produk tidak ditemukan. Cek /produk")
    elif cmd == "/laporan":
        telegram.send(analis.weekly_report(cfg, state))
    elif cmd == "/jadwal":
        telegram.send(jadwal.teks(cfg, state, besok=arg.lower().startswith("besok")))
    elif cmd == "/status":
        rows = [f"{'🟢' if a['status'] == 'idle' else '🟠'} <b>{esc(a['name'])}</b>\n   {esc(a['last'])} ({a['at']})"
                for a in state.d["agents"].values()]
        mode = "OTOMATIS" if state.auto_publish(cfg) else "PERLU PERSETUJUAN"
        telegram.send(f"🏢 <b>Status kantor</b> — mode {mode}\nTerbit: {state.d['stats']['published']} | Draft: {state.d['stats']['drafts']}\n\n" + "\n".join(rows))
    elif cmd == "/otomatis":
        state.d["auto_publish"] = arg.lower() == "on"
        telegram.send(f"⚙️ Mode terbit otomatis: <b>{'ON' if state.d['auto_publish'] else 'OFF'}</b>")
    else:
        telegram.send("Perintah tidak dikenal. Ketik /bantuan")


def handle_callback(cfg, state, cb):
    action, _, did = cb.get("data", "").partition(":")
    if not VIA_WEBHOOK:
        telegram.answer_callback(cb["id"])
    mapping = {"ok": "/setuju", "now": "/terbit", "no": "/tolak", "redo": "/revisi"}
    if action in mapping:
        handle_command(cfg, state, f"{mapping[action]} {did}")


def handle_update(cfg, state, upd):
    owner = str(telegram.owner_chat())
    msg = upd.get("message") or {}
    cb = upd.get("callback_query")
    chat = str((msg.get("chat") or {}).get("id") or ((cb or {}).get("message", {}).get("chat", {}).get("id")))
    if owner and chat != owner:
        telegram.send("⛔ Maaf, kantor ini hanya menerima perintah dari pemilik.", chat_id=chat)
        return
    state.work("kepala", "Menerima perintah dari Bos")
    try:
        if cb:
            handle_callback(cfg, state, cb)
        elif msg.get("text", "").startswith("/"):
            handle_command(cfg, state, msg["text"])
        elif msg.get("text"):
            # pesan bebas = permintaan topik
            ack("👷 Saya anggap itu topik konten baru. Tim mulai bekerja...")
            create_draft(cfg, state, topic=msg["text"])
    except Exception as e:
        telegram.send(f"⚠️ Ada kendala: {esc(e)}")
        print("ERROR", e)
    state.done("kepala", "Perintah selesai diproses")


def harga_pagi(cfg, state):
    """Cek harga di lynk.id sekali sehari (slot pertama); kabari Bos hanya bila ada perubahan."""
    if state.d.get("harga", {}).get("sync", {}).get("at", "")[:10] == now_wit().date().isoformat():
        return
    try:
        ubah = harga.sync_lynk(cfg, state)
    except Exception as e:
        print("sinkron harga gagal:", e)
        return
    if ubah:
        telegram.send("💰 <b>Harga di lynk.id berubah</b> — CTA & promo sudah ikut diperbarui:\n"
                      + "\n".join("• " + esc(u) for u in ubah) + "\nCek: /harga")


# ------------------------------------------------------------------ mode
def run(mode):
    cfg, state = load_config(), State()
    harga.apply(cfg, state)
    try:
        if mode == "daily":
            create_draft(cfg, state)
        elif mode == "poll":
            # Jaga kantor tetap "melek" selama POLL_SECONDS (default 4,5 menit) dengan long polling,
            # jadi bot membalas dalam hitungan detik, bukan menunggu putaran berikutnya.
            import time
            webhook = ((telegram.raw("getWebhookInfo") or {}).get("result") or {}).get("url")
            end = time.time() + (0 if webhook else int(os.environ.get("POLL_SECONDS", "270")))
            humas.publish_due(cfg, state)
            while time.time() < end:
                wait = max(1, min(25, int(end - time.time())))
                t0 = time.time()
                batch = telegram.get_updates(state.d["tg_offset"], wait=wait)
                if not batch and time.time() - t0 < 1:
                    time.sleep(3)  # token salah/koneksi putus: jangan membanjiri API
                for upd in batch:
                    state.d["tg_offset"] = upd["update_id"] + 1
                    state.save()  # simpan offset dulu agar perintah tidak terulang bila error
                    handle_update(cfg, state, upd)
                    state.save()
            humas.publish_due(cfg, state)
        elif mode == "cek":
            from . import diagnosa
            diagnosa.run(cfg, state)
        elif mode == "event":
            global VIA_WEBHOOK
            VIA_WEBHOOK = True
            raw = os.environ.get("UPDATE_JSON", "").strip()
            if raw:
                upd = json.loads(raw)
            else:
                ev = json.load(open(os.environ["GITHUB_EVENT_PATH"]))
                upd = (ev.get("client_payload") or {}).get("update")
            if upd:
                handle_update(cfg, state, upd)
            humas.publish_due(cfg, state)
        elif mode == "slot":
            if int(os.environ.get("SLOT", "0")) == 0 and cfg.get("harga_sync_lynk"):
                harga_pagi(cfg, state)
            run_slot(cfg, state, int(os.environ.get("SLOT", "0")))
            humas.publish_due(cfg, state)
        elif mode == "weekly":
            telegram.send(analis.weekly_report(cfg, state))
        elif mode == "demo":
            demo(cfg, state)
        else:
            print(__doc__)
    finally:
        for a in AGENTS:
            if state.d["agents"][a]["status"] != "idle":
                state.d["agents"][a]["status"] = "idle"
        jadwal.snapshot(cfg, state)
        state.save()


def demo(cfg, state):
    content = {
        "hook": "5 Prompt AI yang Bikin Surat Dinas Kelar 5 Menit",
        "subtitle": "Contekan untuk ASN & perangkat desa yang sering lembur bikin naskah",
        "cover_pose": "melipat_tangan",
        "items": [
            {"title": "Surat Undangan Rapat", "sub": "Rapat koordinasi kampung/desa", "icon": "\U0001F4E8"},
            {"title": "Nota Dinas ke Atasan", "sub": "Laporan progres kegiatan", "icon": "\U0001F4DD"},
            {"title": "Notulen Rapat", "sub": "Dari catatan acak jadi rapi", "icon": "\U0001F5D2"},
            {"title": "Ringkasan Regulasi", "sub": "10 poin penting untuk perangkat", "icon": "\U0001F4DA"},
            {"title": "Cek Ulang Sebelum Kirim", "sub": "AI bisa salah, Anda yang tanda tangan", "icon": "\u2705"},
        ],
        "details": [
            {"title": "Surat Undangan Rapat", "body": "Prompt: \"Buatkan surat undangan rapat koordinasi dari Kepala Kampung kepada Ketua RT/RW, hari Senin pukul 09.00 WIT di balai kampung, sesuai format tata naskah dinas.\""},
            {"title": "Nota Dinas ke Atasan", "body": "Prompt: \"Susun nota dinas dari Kepala Seksi kepada Kepala Dinas tentang progres kegiatan bulan ini, maksimal 1 halaman, bahasa baku.\""},
            {"title": "Cek Ulang Sebelum Kirim", "body": "AI membantu menyusun draf, tetapi nomor surat, nama pejabat, dan dasar hukum tetap wajib dicek sesuai regulasi yang berlaku di instansi Anda."},
        ],
        "note": "Contoh prompt untuk latihan. Sesuaikan dengan tata naskah dinas instansi Anda",
        "cta": "Simpan buat contekan & bagikan ke grup kantor!",
        "caption": "Masih begadang bikin surat dinas? ...",
        "hashtags": ["#ASN", "#AIuntukASN"],
    }
    prod = cfg["products"][0]
    paths = desain.render(cfg, state, "demo", content, "AI untuk Kerja Kantor", "carousel_prompt", prod)
    print("\n".join(paths))


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "")
