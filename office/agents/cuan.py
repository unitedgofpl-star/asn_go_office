"""Bang Cuan — memilih produk lynk.id yang relevan dan menyiapkan CTA penjualan."""
from .. import llm


def pick_product(cfg, state, pillar_id, force=False, product_id=None):
    prods = cfg.get("products", [])
    if not prods:
        return None
    if product_id:
        return next((p for p in prods if p["id"] == product_id), None)
    matches = [p for p in prods if pillar_id in p.get("match_pillars", [])] or prods
    # rotasi agar tidak itu-itu saja
    n = state.d.setdefault("cuan_rot", 0)
    state.d["cuan_rot"] = n + 1
    p = matches[n % len(matches)]
    state.work("cuan", f"Menyiapkan CTA produk: {p['name']}", status="idle" if not force else "working")
    return p


def add_soft_cta(cfg, content, product):
    if not product:
        return content
    line = f"\n\n🛠 Mau lebih cepat? cek {product['name']} — link di bio ({cfg.get('lynk_url', '')})."
    content["caption"] = content.get("caption", "") + line
    return content


def promo_copy(cfg, state, product):
    """Teks broadcast singkat untuk WA/Telegram/Story."""
    state.work("cuan", f"Menulis copy promo {product['name']}")
    out = llm.ask(
        f"Tulis 3 versi copy promosi singkat (maks 60 kata/versi) untuk produk '{product['name']}' "
        f"seharga {product['price']}: {product['pitch']} Target: ASN & perangkat desa. "
        f"Versi 1 untuk Story IG, versi 2 untuk broadcast WhatsApp, versi 3 untuk komentar balasan. "
        f"Sertakan link {product['url']}. Bahasa Indonesia, tidak lebay.")
    state.done("cuan", f"Copy promo {product['name']} siap")
    return out
