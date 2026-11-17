"""Jadwal posting harian: dihitung dari config.slots + catatan eksekusi slot, disimpan ke state.json
(dibaca Cloudflare Worker untuk /jadwal instan dan oleh kantor 3D untuk papan jadwal)."""
import datetime as dt
import html

from .core import now_wit, WIT

TIPE = {"carousel": "Carousel", "berita": "Berita Terkini", "reels": "Reels"}
FMT = {"carousel_tutorial": "Tutorial", "carousel_listicle": "Listicle", "carousel_prompt": "Contekan Prompt",
       "carousel_mitos": "Mitos vs Fakta", "carousel_promo": "Soft-selling"}
IKON = {"terbit": "✅", "menunggu": "⏸", "proses": "🔄", "gagal": "⚠️", "terlewat": "❌", "akan": "🕒", "berikutnya": "⏭"}
LABEL = {"terbit": "Terbit", "menunggu": "Menunggu persetujuan", "proses": "Sedang diproses", "gagal": "Gagal",
         "terlewat": "Tidak jalan (pemicu jadwal telat/mati)", "akan": "Terjadwal", "berikutnya": "Berikutnya"}
TOLERANSI_MENIT = 45  # cron GitHub kadang telat; selama ini dianggap "sedang diproses"


def plan(cfg, idx, day):
    """Rotasi pilar & format per slot (deterministik per tanggal)."""
    slot = cfg["slots"][idx]
    doy = day.timetuple().tm_yday
    order = [p["id"] for p in cfg["pillars"]]
    pillar_id = order[(doy * len(cfg["slots"]) + idx) % len(order)]
    fmts = slot.get("formats") or ["carousel_listicle"]
    return slot, pillar_id, fmts[doy % len(fmts)]


def log_slot(state, idx, did=None, status="proses"):
    day = now_wit().date().isoformat()
    sl = state.d.setdefault("slot_log", {})
    for k in [k for k in sl if k < (now_wit().date() - dt.timedelta(days=7)).isoformat()]:
        del sl[k]
    sl.setdefault(day, {})[str(idx)] = {"did": did, "status": status, "at": now_wit().isoformat(timespec="minutes")}


def rows(cfg, state, day=None):
    now = now_wit()
    day = day or now.date()
    pil = {p["id"]: p.get("name", p["id"]) for p in cfg["pillars"]}
    logd = state.d.get("slot_log", {}).get(day.isoformat(), {})
    used = {v.get("did") for v in logd.values()}
    out = []
    for i in range(len(cfg["slots"])):
        slot, pid, fmt = plan(cfg, i, day)
        h, m = map(int, slot["time"].split(":"))
        when = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=WIT)
        tipe = TIPE.get(slot["type"], slot["type"])
        jenis = f"{tipe} {FMT.get(fmt, '')}".strip() if slot["type"] == "carousel" else tipe
        r = {"slot": i, "jam": slot["time"], "tipe": slot["type"], "jenis": jenis,
             "pilar": "Berita pilihan" if slot["type"] == "berita" else pil.get(pid, pid), "judul": "", "id": ""}
        lg = logd.get(str(i))
        d = state.d["drafts"].get((lg or {}).get("did") or "")
        if d:
            r["id"], r["judul"] = d["id"], d.get("content", {}).get("hook", "")
            r["status"] = {"published": "terbit", "failed": "gagal", "draft": "menunggu", "rejected": "gagal"}.get(d.get("status"), "proses")
            if d.get("published_at"):
                r["terbit"] = d["published_at"][11:16]
        elif lg:
            r["status"] = lg.get("status", "proses")
        elif when <= now:
            r["status"] = "proses" if (now - when).total_seconds() < TOLERANSI_MENIT * 60 else "terlewat"
        else:
            r["status"] = "akan"
        out.append(r)
    nxt = next((r for r in out if r["status"] == "akan"), None)
    if nxt and day == now.date():
        nxt["status"] = "berikutnya"
    return out


def sudah_jalan(state, idx):
    """True bila slot ini hari ini sudah dikerjakan / sedang dikerjakan (cegah dobel dari 2 pemicu jadwal)."""
    lg = state.d.get("slot_log", {}).get(now_wit().date().isoformat(), {}).get(str(idx))
    if not lg or lg.get("status") == "gagal":
        return False
    if lg.get("did"):
        return True
    t = dt.datetime.fromisoformat(lg["at"])
    return (now_wit() - t).total_seconds() < 40 * 60


def manual(state, day, slot_rows=None):
    """Draft hasil perintah manual (/buat, /reels, ...) pada tanggal itu."""
    slot_ids = {r.get("id") for r in (slot_rows or [])} | {v.get("did") for v in state.d.get("slot_log", {}).get(day.isoformat(), {}).values()}
    res = []
    for d in state.d["drafts"].values():
        t = d.get("published_at") or d.get("scheduled_at") or d.get("created", "")
        if d["id"] in slot_ids or not t.startswith(day.isoformat()) or d.get("status") == "rejected":
            continue
        res.append({"jam": t[11:16], "id": d["id"], "jenis": TIPE.get(d.get("type", "carousel"), "Carousel"),
                    "judul": d.get("content", {}).get("hook", ""),
                    "status": {"published": "terbit", "failed": "gagal", "draft": "menunggu", "approved": "proses"}.get(d.get("status"), "proses")})
    return sorted(res, key=lambda x: x["jam"])


def snapshot(cfg, state):
    """Simpan jadwal hari ini & besok ke state (dibaca Worker /jadwal dan kantor 3D)."""
    try:
        today = now_wit().date()
        tom = today + dt.timedelta(days=1)
        state.d["jadwal"] = {
            "tanggal": today.isoformat(), "dibuat": now_wit().isoformat(timespec="minutes"),
            "hari_ini": (hr := rows(cfg, state, today)), "manual": manual(state, today, hr),
            "besok_tanggal": tom.isoformat(), "besok": [dict(r, status="akan") for r in rows(cfg, state, tom)],
            "otomatis": bool(cfg.get("slot_autopublish", True)),
        }
    except Exception as e:  # jadwal tidak boleh menggagalkan kerja utama
        print("jadwal snapshot gagal:", e)


HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def tgl(day):
    return f"{HARI[day.weekday()]}, {day.day} {BULAN[day.month]} {day.year}"


def teks(cfg, state, besok=False):
    e = html.escape
    now = now_wit()
    day = now.date() + dt.timedelta(days=1 if besok else 0)
    rs = rows(cfg, state, day)
    if besok:
        rs = [dict(r, status="akan") for r in rs]
    lines = [f"📅 <b>Jadwal posting {'besok' if besok else 'hari ini'}</b>\n{tgl(day)} • jam WIT\n"]
    for r in rs:
        st = r["status"]
        ln = f"{IKON[st]} <b>{r['jam']}</b> {e(r['jenis'])} • {e(r['pilar'])}"
        if r.get("judul"):
            ln += f"\n      “{e(r['judul'][:70])}”"
        if st not in ("akan",):
            ln += f"\n      <i>{LABEL[st]}{(' ' + r['terbit']) if r.get('terbit') else ''}</i>" + (f" #{r['id']}" if r.get("id") else "")
        lines.append(ln)
    if not besok:
        man = manual(state, day, rs)
        if man:
            lines.append("\n✍️ <b>Konten manual hari ini</b>")
            lines += [f"{IKON[m['status']]} {m['jam']} {e(m['jenis'])} #{m['id']} — {e(m['judul'][:60])}" for m in man]
        done = sum(r["status"] == "terbit" for r in rs) + sum(m["status"] == "terbit" for m in man)
        nxt = next((r for r in rs if r["status"] == "berikutnya"), None)
        lines.append(f"\n📊 Terbit hari ini: <b>{done}</b> • Terjadwal: {len(rs)} slot")
        if nxt:
            h, m = map(int, nxt["jam"].split(":"))
            mins = int((dt.datetime(day.year, day.month, day.day, h, m, tzinfo=WIT) - now).total_seconds() // 60)
            lines.append(f"⏭ Berikutnya {nxt['jam']} WIT ({mins // 60} jam {mins % 60} menit lagi): {e(nxt['jenis'])}")
    mode = "terbit otomatis" if cfg.get("slot_autopublish", True) else "menunggu persetujuan Bos"
    lines.append(f"⚙️ Slot terjadwal: {mode} (kecuali QC risiko tinggi).\nLihat besok: /jadwal besok")
    return "\n".join(lines)
