"""Bu Naskah (penulis) & Pak Verifikator (QC) — membuat dan memeriksa konten carousel."""
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
 "cover_pose": "melipat_tangan | presentasi | berdiri",
 "items": [{"title": "maks 5 kata", "sub": "maks 9 kata", "icon": "1 emoji yang mewakili"}],
 "details": [{"title": "sama dengan salah satu items.title", "body": "penjelasan praktis maks 45 kata"}],
 "note": "catatan kaki/disclaimer singkat maks 16 kata (mis. 'Cek regulasi terbaru di instansi Anda')",
 "cta": "ajakan maks 14 kata",
 "caption": "caption 80-150 kata, ditulis sebagai Cicilia (orang pertama): hook baris pertama, ringkasan isi, ajakan SIMPAN & BAGIKAN, pertanyaan untuk komentar",
 "hashtags": ["#..."]
}
items berisi 4-6 butir (ditampilkan sebagai daftar bernomor). details berisi 2-5 butir terpenting untuk dijelaskan per slide."""


def _system(cfg):
    b = cfg["brand"]
    inf = cfg.get("influencer", {})
    persona = (f"Wajah akun adalah virtual influencer AI bernama {inf.get('name', 'Cicilia')}: {inf.get('persona', '')} "
               if inf else "")
    return (f"Anda adalah Bu Naskah, content writer senior akun Instagram {b['handle']} ({b['tagline']}). {persona}"
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


def write(cfg, state, pillar, topic, fmt, news=None, product=None, notes=None):
    state.work("naskah", f"Menulis carousel: {topic[:50]}")
    prompt = f"Pilar: {pillar['name']}\nTopik: {topic}\nFormat: {FORMATS.get(fmt, FORMATS['carousel_listicle'])}\n"
    if news:
        prompt += "\nBerita tren minggu ini (pakai sebagai inspirasi sudut pandang, JANGAN mengutip angka yang tidak ada):\n" + "\n".join(news) + "\n"
    if product:
        prompt += (f"\nProduk yang boleh disebut di slide terakhir/caption: {product['name']} ({product['price']}) — {product['pitch']} "
                   "Arahkan ke 'link di bio'.\n")
    if notes:
        prompt += f"\nCATATAN REVISI DARI BOS (wajib dipenuhi): {notes}\n"
    prompt += "\n" + SCHEMA
    content = llm.ask(prompt, _system(cfg), as_json=True)
    state.done("naskah", f"Draft selesai: \"{content.get('hook', '')}\"")
    return content


def verify(cfg, state, content):
    """Pak Verifikator memeriksa fakta, regulasi, dan kepatuhan; mengembalikan versi aman."""
    state.work("qc", "Mengecek fakta, regulasi & bahasa...")
    prompt = (
        "Periksa konten carousel JSON berikut untuk akun edukasi ASN/pemerintahan desa.\n"
        "Pastikan struktur JSON tetap (hook, subtitle, cover_pose, items, details, note, cta, caption, hashtags). Cek: (1) klaim regulasi/angka yang berpotensi salah atau dikarang → hapus nomornya atau ubah jadi umum; "
        "(2) saran yang melanggar aturan/etika ASN atau keamanan data; (3) typo & EYD; (4) panjang teks per slide (maks 45 kata).\n"
        "Balas JSON: {\"issues\": [\"...\"], \"risk\": \"rendah|sedang|tinggi\", \"content\": <konten yang sudah diperbaiki, struktur sama persis>}\n\n"
        f"KONTEN:\n{content}"
    )
    try:
        res = llm.ask(prompt, "Anda Pak Verifikator, editor & pemeriksa fakta yang teliti di bidang pemerintahan Indonesia.", as_json=True)
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
