"""Harga produk lynk.id: satu sumber kebenaran untuk CTA, slide promo, Reels & copy promo.

Harga dasar ada di config.yaml (bagian `paket:`). Perubahan lewat Telegram (/harga) atau sinkron otomatis
dari halaman lynk.id disimpan di state.json, lalu dipakai semua konten berikutnya.
"""
import html
import json
import re

import requests

from .core import now_wit


def rp(n):
    return "Rp" + f"{int(n):,}".replace(",", ".")


def parse_angka(t):
    """'149000' / '149.000' / 'Rp149rb' / '149k' / '1,2jt' → int, atau None."""
    t = str(t).lower().replace("rp", "").replace(" ", "")
    m = re.fullmatch(r"([\d.,]+)(rb|ribu|k|jt|juta)?", t)
    if not m:
        return None
    num, suf = m.group(1), m.group(2)
    if suf in ("jt", "juta"):
        v = float(num.replace(".", "").replace(",", "."))
        return int(v * 1_000_000)
    if suf in ("rb", "ribu", "k"):
        v = float(num.replace(".", "").replace(",", "."))
        return int(v * 1000)
    v = int(num.replace(".", "").replace(",", ""))
    return v if v >= 1000 else None


def paket_aktif(cfg, state):
    """Gabungan config + perubahan tersimpan: {id: {nama, harga, normal, ket}}."""
    over = state.d.get("harga", {}).get("paket", {})
    out = {}
    for p in cfg.get("paket", []):
        o = over.get(p["id"], {})
        out[p["id"]] = {"id": p["id"], "nama": p["nama"], "ket": p.get("ket", ""),
                        "harga": int(o.get("harga", p["harga"])), "normal": o.get("normal", p.get("normal"))}
    return out


def _label(pk, ket=True):
    s = f"{pk['nama']} {rp(pk['harga'])}"
    if pk.get("normal") and int(pk["normal"]) > pk["harga"]:
        s += f" (normal {rp(pk['normal'])})"
    if ket and pk.get("ket"):
        s += f" — {pk['ket']}"
    return s


def apply(cfg, state):
    """Tulis ulang price & pitch setiap produk dari harga paket terkini (dipanggil tiap kali kantor jalan)."""
    pk = paket_aktif(cfg, state)
    if not pk:
        return cfg
    for prod in cfg.get("products", []):
        ids = [i for i in prod.get("paket", []) if i in pk]
        if not ids:
            continue
        items = [pk[i] for i in ids]
        if len(items) == 1:
            it = items[0]
            prod["price"] = rp(it["harga"]) + (f" (normal {rp(it['normal'])})" if it.get("normal") and int(it["normal"]) > it["harga"] else "") + \
                (f" ({it['ket'].split(' + ')[0]})" if it.get("ket") else "")
        else:
            prod["price"] = f"mulai {rp(min(i['harga'] for i in items))} (sekali bayar)"
        base = prod.get("_pitch_base") or re.sub(r"\s*Paket:.*$", "", prod.get("pitch", ""), flags=re.S).strip()
        prod["_pitch_base"] = base
        prod["pitch"] = base + (" Paket: " + " · ".join(_label(i) for i in items) + "." if len(items) > 1 else "")
    return cfg


def set_harga(cfg, state, pid, harga, normal=None, sumber="telegram"):
    h = state.d.setdefault("harga", {}).setdefault("paket", {})
    h[pid] = {"harga": int(harga), "normal": int(normal) if normal else None,
              "sumber": sumber, "diubah": now_wit().isoformat(timespec="minutes")}
    apply(cfg, state)


def ringkas(cfg, state):
    e = html.escape
    pk = paket_aktif(cfg, state)
    over = state.d.get("harga", {}).get("paket", {})
    rows = []
    for p in pk.values():
        o = over.get(p["id"])
        asal = f" <i>(diubah {o['diubah'][5:16].replace('T', ' ')} via {o.get('sumber', '-')})</i>" if o else ""
        rows.append(f"• <code>{p['id']}</code> {e(_label(p, ket=False))}{asal}")
    prods = "\n".join(f"• {e(x['name'])}: <b>{e(x['price'])}</b>" for x in cfg.get("products", []))
    contoh = next((x for x in cfg.get("products", []) if x.get("paket")), None)
    cta = (f"🛠 Capek ngetik surat dinas dari nol? {contoh['name']} — {contoh['price']}. Cek link di bio 👉 {cfg.get('lynk_url', '')}"
           if contoh else "")
    sync = state.d.get("harga", {}).get("sync", {})
    sline = f"\n🔄 Sinkron lynk.id terakhir: {sync.get('at', '-')[:16].replace('T', ' ')} — {e(sync.get('hasil', '-'))}" if sync else ""
    return ("💰 <b>Harga paket saat ini</b>\n" + "\n".join(rows) +
            f"\n\n🛒 <b>Tampil di konten sebagai</b>\n{prods}\n\n📣 <b>Contoh CTA</b>\n<i>{e(cta)}</i>{sline}\n\n"
            "<b>Cara ubah:</b>\n<code>/harga pro 149000</code>\n<code>/harga pro 149rb normal 179rb</code> (harga coret/promo)\n"
            "<code>/harga sync</code> — ambil harga terbaru otomatis dari lynk.id\n<code>/harga reset</code> — kembali ke harga di config")


# ------------------------------------------------------------------ sinkron dari lynk.id
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "id-ID,id;q=0.9"}
KEY_NAMA = ("title", "name", "product_name", "productName", "judul")
KEY_HARGA = ("price", "final_price", "finalPrice", "sale_price", "salePrice", "selling_price", "amount", "harga")
KEY_NORMAL = ("original_price", "originalPrice", "normal_price", "strike_price", "strikePrice", "compare_price", "price_before")


def _walk(o, out):
    if isinstance(o, dict):
        nama = next((o[k] for k in KEY_NAMA if isinstance(o.get(k), str)), None)
        harga = next((o[k] for k in KEY_HARGA if o.get(k) not in (None, "")), None)
        if nama and harga is not None:
            h = parse_angka(harga) if not isinstance(harga, (int, float)) else int(harga)
            n = next((o[k] for k in KEY_NORMAL if o.get(k)), None)
            n = (parse_angka(n) if not isinstance(n, (int, float)) else int(n)) if n else None
            if h:
                out.append({"nama": nama, "harga": h, "normal": n})
        for v in o.values():
            _walk(v, out)
    elif isinstance(o, list):
        for v in o:
            _walk(v, out)


def baca_lynk(url):
    """Kembalikan daftar {nama, harga, normal} dari halaman toko lynk.id (best effort)."""
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    t = r.text
    items = []
    for m in re.finditer(r'<script[^>]*(?:__NEXT_DATA__|application/(?:ld\+)?json)[^>]*>(.*?)</script>', t, re.S):
        try:
            _walk(json.loads(m.group(1)), items)
        except Exception:
            pass
    if not items:  # cadangan: teks biasa "Nama produk ... Rp99.000"
        from bs4 import BeautifulSoup
        txt = BeautifulSoup(t, "html.parser").get_text("\n", strip=True)
        lines = [x for x in txt.split("\n") if x.strip()]
        for i, ln in enumerate(lines):
            m = re.search(r"Rp\s?([\d.]{4,})", ln)
            if m:
                nama = next((lines[j] for j in range(i - 1, max(-1, i - 4), -1) if not re.search(r"Rp\s?\d", lines[j]) and len(lines[j]) > 3), "")
                hs = [parse_angka(x) for x in re.findall(r"Rp\s?([\d.]{4,})", ln)]
                hs = [h for h in hs if h]
                if nama and hs:
                    items.append({"nama": nama, "harga": min(hs), "normal": max(hs) if len(hs) > 1 else None})
    uniq = {}
    for it in items:
        uniq.setdefault((it["nama"].strip().lower(), it["harga"]), it)
    return list(uniq.values())


def sync_lynk(cfg, state):
    """Cocokkan produk di lynk.id dengan paket (kata kunci di config `paket[].cocok`). Kembalikan daftar perubahan."""
    url = cfg.get("lynk_url")
    hasil = {"at": now_wit().isoformat(timespec="minutes")}
    try:
        items = baca_lynk(url)
    except Exception as e:
        hasil["hasil"] = f"gagal membuka lynk.id ({str(e)[:60]})"
        state.d.setdefault("harga", {})["sync"] = hasil
        return None
    pk = paket_aktif(cfg, state)
    ubah = []
    for p in cfg.get("paket", []):
        kunci = [k.lower() for k in p.get("cocok", [p["nama"]])]
        cand = [it for it in items if all(re.search(rf"\b{re.escape(k)}\b", it["nama"].lower()) for k in kunci)]
        if not cand:
            continue
        it = min(cand, key=lambda x: len(x["nama"]))
        lama = pk[p["id"]]
        if it["harga"] != lama["harga"] or (it.get("normal") or None) != (lama.get("normal") or None):
            set_harga(cfg, state, p["id"], it["harga"], it.get("normal"), sumber="lynk.id")
            ubah.append(f"{p['nama']}: {rp(lama['harga'])} → {rp(it['harga'])}" + (f" (normal {rp(it['normal'])})" if it.get("normal") else ""))
    hasil["hasil"] = (f"{len(items)} produk terbaca, {len(ubah)} harga berubah" if items
                      else "halaman terbuka tapi harga tidak terbaca")
    state.d.setdefault("harga", {})["sync"] = hasil
    return ubah
