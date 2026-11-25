"""Kaka Selfina (penulis) & Kaka Agus (QC) — membuat dan memeriksa konten carousel."""
import random

from .. import llm

FORMATS = {
    "carousel_tutorial": "Tutorial langkah-demi-langkah (Langkah 1, 2, 3...). Setiap slide 1 langkah konkret yang bisa langsung dipraktikkan.",
    "carousel_listicle": "Listicle: 'X cara/tools/kesalahan...'. Setiap slide 1 poin + penjelasan singkat + contoh nyata di kantor/desa.",
    "carousel_prompt": "Contekan prompt AI: setiap slide berisi 1 kebutuhan kerja (judul) dan isi berupa PROMPT siap salin dalam tanda kutip, diawali 'Prompt:'.",
    "carousel_mitos": "Mitos vs Fakta: judul slide diawali 'MITOS:' lalu isi diawali 'FAKTA:' dengan penjelasan.",
    "carousel_promo": "Soft-selling: angkat masalah nyata (pain point) audiens, tunjukkan solusi, lalu perkenalkan produk sebagai jalan pintas. Edukatif dulu, jualan belakangan.",
}

SCHEMA = """Balas HANYA JSON dengan struktur:
{
 "hook": "judul cover gaya headline berita, 6-10 kata, bikin penasaran (contoh: '6 Aplikasi Gratis yang Bikin Laporan Desa Kelar Sehari')",
 "subtitle": "sub-judul cover maks 12 kata",
 "mood": "suasana ekspresi Cicilia yang paling cocok dengan isi: ceria | semangat | terkejut | cemberut | tegas | sedih | sayang | tenang | menjelaskan (mis. kesalahan umum → cemberut/tegas, mitos → terkejut, beban lembur → sedih, tips → ceria/semangat, promo → sayang)",
 "items": [{"title": "maks 5 kata", "sub": "maks 9 kata", "icon": "1 emoji yang mewakili"}],
 "details": [{"title": "SAMA PERSIS dengan items.title pada urutan yang sama", "body": "penjelasan praktis maks 45 kata"}],
 "note": "catatan kaki/disclaimer singkat maks 16 kata (mis. 'Cek regulasi terbaru di instansi Anda')",
 "cta": "ajakan maks 14 kata",
 "caption": "caption 80-150 kata, ditulis sebagai Cicilia (orang pertama): hook baris pertama, ringkasan isi, ajakan SIMPAN & BAGIKAN, pertanyaan untuk komentar",
 "hashtags": ["#..."]
}
items berisi 3-5 butir (ditampilkan sebagai daftar bernomor). details WAJIB berjumlah SAMA dengan items:
setiap butir items dijelaskan di 1 slide sendiri, urutannya sama (poin 1 → detail 1, dst). Jangan ada poin tanpa penjelasan."""


def _system(cfg):
    b = cfg["brand"]
    inf = cfg.get("influencer", {})
    persona = (f"Wajah akun adalah {inf.get('name', 'Cicilia')}: {inf.get('persona', '')} "
               "Jangan menulis bahwa Cicilia adalah AI/virtual influencer dan jangan menulis 'ilustrasi AI' di caption atau slide. "
               if inf else "")
    return (f"Anda adalah Kaka Selfina, content writer senior akun Instagram {b['handle']} ({b['tagline']}). {persona}"
            f"Audiens: {b['audience']} Gaya bahasa: {b['voice']} "
            "Konten edukatif ala carousel 'save-worthy': hook kuat, isi padat, langsung praktik. "
            "ATURAN KEAMANAN: jangan mengarang nomor/tahun peraturan, angka anggaran, atau nama pejabat. "
            "Jika menyebut regulasi, sebut hanya yang Anda yakin benar dan umum (mis. 'Permendagri tentang Pedoman Tata Naskah Dinas') "
            "tanpa nomor jika ragu, dan sarankan pembaca mengecek regulasi terbaru. Jangan memuat isu SARA atau politik praktis.")


def pick_topic(cfg, pillar_id):
    pillars = cfg["pillars"]
    if pillar_id in (None, "any"):
        p = random.choice(pillars)
    else:
        p = next((x for x in pillars if x["id"] == pillar_id), pillars[0])
    return p, random.choice(p["topics"])


def write(cfg, state, pillar, topic, fmt, news=None, product=None, notes=None, avoid=None):
    state.work("naskah", f"Menulis carousel: {topic[:50]}")
    prompt = f"Pilar: {pillar['name']}\nTopik: {topic}\nFormat: {FORMATS.get(fmt, FORMATS['carousel_listicle'])}\n"
    if news:
        prompt += "\nBerita tren minggu ini (pakai sebagai inspirasi sudut pandang, JANGAN mengutip angka yang tidak ada):\n" + "\n".join(news) + "\n"
    if product:
        prompt += (f"\nProduk yang boleh disebut di slide terakhir/caption: {product['name']} ({product['price']}) — {product['pitch']} "
                   "Arahkan ke 'link di bio'.\n")
    if notes:
        prompt += f"\nCATATAN REVISI DARI BOS (wajib dipenuhi): {notes}\n"
    if avoid:
        prompt += "\nJangan mengulang judul/sudut pandang yang sudah pernah terbit ini: " + "; ".join(avoid[-15:]) + "\n"
    prompt += "\n" + SCHEMA
    content = llm.ask(prompt, _system(cfg), as_json=True)
    state.done("naskah", f"Draft selesai: \"{content.get('hook', '')}\"")
    return content


def verify(cfg, state, content):
    """Kaka Agus memeriksa fakta, regulasi, dan kepatuhan; mengembalikan versi aman."""
    state.work("qc", "Mengecek fakta, regulasi & bahasa...")
    prompt = (
        "Periksa konten carousel JSON berikut untuk akun edukasi ASN/pemerintahan desa.\n"
        "Pastikan struktur JSON tetap (hook, subtitle, mood, items, details, note, cta, caption, hashtags). Cek: (1) klaim regulasi/angka yang berpotensi salah atau dikarang → hapus nomornya atau ubah jadi umum; "
        "(2) saran yang melanggar aturan/etika ASN atau keamanan data; (3) typo & EYD; (4) panjang teks per slide (maks 45 kata).\n"
        "Balas JSON: {\"issues\": [\"...\"], \"risk\": \"rendah|sedang|tinggi\", \"content\": <konten yang sudah diperbaiki, struktur sama persis>}\n\n"
        f"KONTEN:\n{content}"
    )
    try:
        res = llm.ask(prompt, "Anda Kaka Agus, editor & pemeriksa fakta yang teliti di bidang pemerintahan Indonesia.", as_json=True)
        fixed = res.get("content") or content
        if not isinstance(fixed, dict) or "items" not in fixed:
            fixed = content
        fixed["_qc"] = {"issues": res.get("issues", []), "risk": res.get("risk", "rendah")}
    except Exception as e:
        fixed = content
        fixed["_qc"] = {"issues": [f"QC gagal dijalankan: {e}"], "risk": "sedang"}
    state.done("qc", f"QC selesai — risiko {fixed['_qc']['risk']}, {len(fixed['_qc']['issues'])} catatan")
    return fixed


def ideas(cfg, state, n=10):
    state.work("naskah", "Brainstorm ide konten...")
    pillars = ", ".join(p["name"] for p in cfg["pillars"])
    out = llm.ask(f"Buat {n} ide judul carousel viral & edukatif untuk pilar: {pillars}. "
                  "Format daftar bernomor, setiap ide 1 baris + [pilar] di akhir.", _system(cfg))
    state.done("naskah", f"{n} ide konten siap")
    return out


def _kunci(t):
    import re
    return re.sub(r"[^a-z0-9]", "", str(t).lower())


def lengkapi_detail(cfg, state, content):
    """Pastikan SETIAP poin di daftar punya slide penjelasan, urut sesuai daftar."""
    items = content.get("items") or []
    if not items:
        return content
    items = items[:6]
    content["items"] = items
    ada = {_kunci(d.get("title")): d for d in content.get("details") or [] if d.get("body")}
    sisa = [d for d in content.get("details") or [] if d.get("body")]
    hasil, kurang = [], []
    for i, it in enumerate(items):
        k = _kunci(it.get("title"))
        d = ada.get(k) or next((x for x in sisa if k and (k in _kunci(x.get("title")) or _kunci(x.get("title")) in k)), None)
        if d:
            sisa = [x for x in sisa if x is not d]
            hasil.append({**d, "title": it.get("title", d.get("title"))})
        else:
            hasil.append(None)
            kurang.append(i)
    if kurang:
        state.work("naskah", f"Melengkapi penjelasan {len(kurang)} poin yang belum ada slidenya")
        try:
            daftar = "\n".join(f"{i + 1}. {items[i].get('title')} — {items[i].get('sub', '')}" for i in kurang)
            r = llm.ask(f"Judul konten: {content.get('hook')}\nTulis penjelasan praktis (maks 45 kata, format sama seperti poin lain) "
                        f"untuk poin berikut:\n{daftar}\nBalas HANYA JSON: {{\"details\": [{{\"title\": \"judul poin persis\", \"body\": \"...\"}}]}}",
                        _system(cfg), as_json=True)
            baru = [x for x in (r.get("details") or []) if x.get("body")]
        except Exception as e:
            print("melengkapi detail gagal:", e)
            baru = []
        for j, i in enumerate(kurang):
            b = baru[j] if j < len(baru) else {"body": items[i].get("sub", "")}
            hasil[i] = {"title": items[i].get("title"), "body": b.get("body", "")}
    content["details"] = hasil
    return content
