"""Pak Kepala — manajer kantor. Menjalankan rutinitas dan menerima perintah Bos lewat Telegram.

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

from . import telegram
from .core import State, load_config, now_wit, WIT, AGENTS
from .agents import riset, naskah, desain, humas, cuan, analis, foto

HELP = """🏢 <b>Kantor Virtual ASN GO Digitals</b>
Perintah untuk Bos:

/buat [topik] — buat carousel baru (topik opsional)
/buat_promo [id_produk] — carousel soft-selling produk
/ide — 10 ide konten
/antrian — daftar draft
/lihat [id] — pratinjau ulang draft
/setuju [id] — setujui (terbit sesuai jadwal)
/terbit [id] — terbitkan sekarang
/revisi [id] [catatan] — tulis ulang dengan catatan
/tolak [id] — buang draft
/promo [id_produk] — copy promosi WA/Story
/produk — daftar produk lynk.id
/laporan — laporan performa
/status — apa yang sedang dikerjakan karyawan
/otomatis on|off — terbit tanpa persetujuan
/bantuan — menu ini"""

FMT_LABEL = {
    "carousel_tutorial": "Tutorial", "carousel_listicle": "Listicle", "carousel_prompt": "Contekan Prompt",
    "carousel_mitos": "Mitos vs Fakta", "carousel_promo": "Soft-selling",
}


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

    content = naskah.write(cfg, state, pillar, topic, fmt, news=news, product=product if promo else None, notes=notes)
    content = naskah.verify(cfg, state, content)
    if not promo:
        content = cuan.add_soft_cta(cfg, content, product)

    disclosure = cfg.get("influencer", {}).get("disclosure")
    if disclosure and disclosure not in content.get("caption", ""):
        content["caption"] = content.get("caption", "") + "\n\n" + disclosure

    did = base or state.new_draft_id()
    scene = foto.generate_cover(cfg, state, content)
    images = desain.render(cfg, state, did, content, pillar["name"], fmt, product, scene=scene)
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


def preview(cfg, state, did):
    d = state.d["drafts"].get(did)
    if not d:
        telegram.send(f"Draft #{esc(did)} tidak ditemukan.")
        return
    from .core import ROOT
    telegram.send_album([ROOT / p for p in d["images"]])
    qc = d["content"].get("_qc", {})
    issues = "\n".join(f"  • {esc(i)}" for i in qc.get("issues", [])[:5]) or "  • tidak ada"
    when = d["scheduled_at"].replace("T", " ")[:16]
    text = (f"📝 <b>Draft #{did}</b> — {esc(d['pillar'])} • {FMT_LABEL.get(d['format'], d['format'])}\n"
            f"Status: <b>{d['status']}</b> | Jadwal: {when} WIT\n"
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
        telegram.send("👷 Siap Bos! Tim mulai produksi carousel... (± 1–2 menit)")
        create_draft(cfg, state, topic=(text.split(maxsplit=1)[1] if arg else None))
    elif cmd == "/buat_promo":
        telegram.send("💰 Bang Cuan & tim menyiapkan konten soft-selling...")
        create_draft(cfg, state, fmt="carousel_promo", product_id=arg or None)
    elif cmd == "/ide":
        telegram.send("💡 <b>Ide konten dari Bu Naskah:</b>\n\n" + esc(naskah.ideas(cfg, state)))
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
        telegram.send(f"✅ #{arg} disetujui. Terbit {drafts[arg]['scheduled_at'][:16].replace('T', ' ')} WIT.")
    elif cmd == "/terbit":
        drafts[arg]["status"] = "approved"
        drafts[arg]["scheduled_at"] = now_wit().isoformat(timespec="minutes")
        telegram.send(f"🚀 #{arg} masuk antrean terbit (dieksekusi di putaran berikutnya, ± 15 menit).")
    elif cmd == "/tolak":
        drafts[arg]["status"] = "rejected"
        telegram.send(f"🗑 #{arg} dibuang.")
    elif cmd == "/revisi":
        if arg not in drafts:
            telegram.send("Format: /revisi [id] [catatan]")
        else:
            d = drafts[arg]
            telegram.send(f"✍️ Bu Naskah merevisi #{arg}...")
            p = next((x["id"] for x in cfg["pillars"] if x["name"] == d["pillar"]), None)
            create_draft(cfg, state, topic=d["topic"], pillar_id=p, fmt=d["format"],
                         product_id=d.get("product") if d["format"] == "carousel_promo" else None,
                         notes=rest or "buat lebih menarik dan lebih praktis", base=arg)
    elif cmd == "/produk":
        rows = [f"• <code>{p['id']}</code> — {esc(p['name'])} ({p['price']})\n  {p['url']}" for p in cfg.get("products", [])]
        telegram.send("🛒 <b>Produk lynk.id</b>\n" + "\n".join(rows))
    elif cmd == "/promo":
        prod = cuan.pick_product(cfg, state, None, product_id=arg) if arg else (cfg.get("products") or [None])[0]
        telegram.send(esc(cuan.promo_copy(cfg, state, prod)) if prod else "Produk tidak ditemukan. Cek /produk")
    elif cmd == "/laporan":
        telegram.send(analis.weekly_report(cfg, state))
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
            telegram.send("👷 Saya anggap itu topik konten baru. Tim mulai bekerja...")
            create_draft(cfg, state, topic=msg["text"])
    except Exception as e:
        telegram.send(f"⚠️ Ada kendala: {esc(e)}")
        print("ERROR", e)
    state.done("kepala", "Perintah selesai diproses")


# ------------------------------------------------------------------ mode
def run(mode):
    cfg, state = load_config(), State()
    try:
        if mode == "daily":
            create_draft(cfg, state)
        elif mode == "poll":
            # Jaga kantor tetap "melek" selama POLL_SECONDS (default 4,5 menit) dengan long polling,
            # jadi bot membalas dalam hitungan detik, bukan menunggu putaran berikutnya.
            import time
            end = time.time() + int(os.environ.get("POLL_SECONDS", "270"))
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
            ev = json.load(open(os.environ["GITHUB_EVENT_PATH"]))
            upd = (ev.get("client_payload") or {}).get("update")
            if upd:
                handle_update(cfg, state, upd)
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
