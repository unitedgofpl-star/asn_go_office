"""Kaka Maria (riset) + Kaka Selfina (naskah) — carousel BERITA TERKINI dari media tepercaya.

Alur:
1. Cari berita 24–48 jam terakhir via Google News RSS (topik ASN, desa, AI & teknologi),
   hanya dari sumber di daftar `berita.sumber_tepercaya` (config.yaml).
2. Kelompokkan berita yang sama dari beberapa media → pilih cerita yang paling banyak diberitakan & belum pernah dipakai.
3. Buka artikel: ambil teks (untuk dirangkum ulang) dan foto di artikel.
   Foto hanya dipakai dari sumber yang diizinkan (`berita.foto_dari`, default situs pemerintah *.go.id & Wikimedia).
4. Jumlah slide = jumlah foto yang layak (maks 6). Tanpa foto → 1 slide sampul tipografi saja, sisanya di caption.
5. Caption = rangkuman dengan bahasa sendiri + daftar sumber & tautan.
"""
import hashlib
import io
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

import feedparser
import requests
from PIL import Image

from .. import llm

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "id-ID,id;q=0.9"}


def _domain(url):
    try:
        return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _match(dom, lst):
    return any(dom == d or dom.endswith("." + d) or (d.startswith(".") and dom.endswith(d)) for d in lst)


def _norm(t):
    return re.sub(r"[^a-z0-9 ]", " ", t.lower())


# ------------------------------------------------------------------ 1. cari
def search(cfg, pillar_id=None, hours=36):
    bc = cfg.get("berita", {})
    trusted = bc.get("sumber_tepercaya", [])
    qmap = bc.get("kueri", {})
    queries = qmap.get(pillar_id) if pillar_id in qmap else sum(qmap.values(), [])
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = []
    for q in queries:
        url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(f"{q} when:2d") + "&hl=id&gl=ID&ceid=ID:id"
        try:
            feed = feedparser.parse(url)
        except Exception:
            continue
        for e in feed.entries[:25]:
            src = getattr(e, "source", {}) or {}
            sdom = _domain(src.get("href", ""))
            if trusted and not _match(sdom, trusted):
                continue
            pub = None
            if getattr(e, "published_parsed", None):
                pub = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
                if pub < since:
                    continue
            title = re.sub(r"\s+-\s+[^-]+$", "", e.title).strip()
            items.append({"title": title, "gn": e.link, "source": src.get("title", sdom), "domain": sdom,
                          "published": pub.isoformat() if pub else "", "query": q})
    # buang duplikat persis
    seen, out = set(), []
    for it in items:
        k = (_norm(it["title"])[:80], it["domain"])
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def cluster(items):
    groups = []
    for it in items:
        for g in groups:
            if SequenceMatcher(None, _norm(it["title"]), _norm(g[0]["title"])).ratio() > .55:
                if it["domain"] not in {x["domain"] for x in g}:
                    g.append(it)
                break
        else:
            groups.append([it])
    return groups


# ------------------------------------------------------------------ 2. buka artikel
def decode(gn_url):
    try:
        from googlenewsdecoder import gnewsdecoder
        r = gnewsdecoder(gn_url, interval=1)
        if r.get("status") or r.get("success"):
            return r.get("decoded_url")
    except Exception as e:
        print("decode gagal:", e)
    return None


def read_article(url):
    from bs4 import BeautifulSoup
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    def meta(*names):
        for n in names:
            m = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if m and m.get("content"):
                return m["content"].strip()
        return ""
    body = soup.find("article") or soup.find("main") or soup.body or soup
    paras = [p.get_text(" ", strip=True) for p in body.find_all("p")]
    paras = [p for p in paras if len(p) > 60 and not re.search(r"(baca juga|simak|copyright|hak cipta|ikuti kami)", p, re.I)]
    imgs = []
    og = meta("og:image", "twitter:image")
    if og:
        imgs.append({"src": urllib.parse.urljoin(url, og), "alt": meta("og:image:alt") or meta("og:title")})
    for fig in body.find_all(["figure", "img"])[:30]:
        im = fig if fig.name == "img" else fig.find("img")
        if not im:
            continue
        src = im.get("data-src") or im.get("data-lazy-src") or im.get("src") or ""
        if not src or src.startswith("data:") or re.search(r"(logo|icon|avatar|banner|ads|sprite|\.svg|\.gif)", src, re.I):
            continue
        cap = fig.find("figcaption").get_text(" ", strip=True) if fig.name == "figure" and fig.find("figcaption") else (im.get("alt") or "")
        imgs.append({"src": urllib.parse.urljoin(url, src), "alt": cap[:200]})
    return {"url": url, "title": meta("og:title") or (soup.title.string.strip() if soup.title else ""),
            "description": meta("og:description", "description"), "text": "\n".join(paras)[:4000], "images": imgs}


def _ahash(im):
    g = im.convert("L").resize((8, 8))
    px = list(g.getdata())
    avg = sum(px) / 64
    return sum(1 << i for i, v in enumerate(px) if v > avg)


def fetch_images(cands, limit=6):
    out, hashes = [], []
    for c in cands:
        if len(out) >= limit:
            break
        try:
            r = requests.get(c["src"], headers=UA, timeout=20)
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception:
            continue
        if im.width < 700 or im.height < 420:
            continue
        h = _ahash(im)
        if any(bin(h ^ x).count("1") < 8 for x in hashes):  # foto sama/mirip
            continue
        hashes.append(h)
        out.append({**c, "img": im})
    return out


# ------------------------------------------------------------------ 3. rangkum
SCHEMA = """Balas HANYA JSON:
{
 "judul": "judul berita versimu sendiri, maks 11 kata, jelas & informatif (bukan clickbait)",
 "sub": "1 kalimat inti berita, maks 18 kata",
 "pilar": "asn | desa | ai",
 "slide_foto": [{"foto": <nomor foto>, "teks": "penjelasan bagian berita yang cocok dengan foto itu, maks 32 kata"}],
 "poin": ["3-5 poin penting untuk pembaca ASN/perangkat desa"],
 "dampak": "1-2 kalimat: apa artinya bagi ASN/perangkat desa",
 "caption": "rangkuman 120-200 kata dengan bahasamu sendiri: apa yang terjadi, siapa, kapan, apa dampaknya; ajak diskusi di komentar",
 "hashtags": ["#..."]
}"""


def summarize(cfg, state, articles, photos):
    from .naskah import _system
    src = "\n\n".join(f"[SUMBER {i + 1}: {a['source']} — {a['url']}]\nJudul: {a['title']}\nRingkasan: {a['description']}\nIsi: {a['text'][:2500]}"
                      for i, a in enumerate(articles))
    fotos = "\n".join(f"Foto {i + 1}: {p.get('alt') or '(tanpa keterangan)'} — dari {p['source']}" for i, p in enumerate(photos)) or "(tidak ada foto)"
    prompt = ("Rangkum berita berikut untuk akun edukasi ASN & pemerintahan desa.\n"
              "ATURAN: tulis ulang dengan bahasamu sendiri (jangan menyalin kalimat sumber, kutipan langsung maks 1 dan < 15 kata), "
              "gunakan HANYA fakta yang ada di sumber, jangan menambah angka/nama/regulasi yang tidak disebut, netral (tanpa opini politik). "
              f"Buat tepat {len(photos)} item slide_foto (satu per foto, urut foto 1..{len(photos)}); jika tidak ada foto, slide_foto kosong.\n\n"
              f"{src}\n\nDAFTAR FOTO:\n{fotos}\n\n{SCHEMA}")
    return llm.ask(prompt, _system(cfg), as_json=True)


# ------------------------------------------------------------------ orkestrasi
def _pakai(state, g, arts, photos):
    state.d.setdefault("news_used", []).extend(_norm(x["title"])[:60] for x in g)
    state.d["news_used"] = state.d["news_used"][-300:]
    state.done("riset", f"Berita: \"{arts[0]['title'][:60]}\" ({len(arts)} sumber, {len(photos)} foto)")
    return arts, photos


def gather(cfg, state, pillar_id=None, topic=None):
    """Kembalikan (articles, photos) untuk satu cerita, atau (None, None) bila tak ada berita baru."""
    bc = cfg.get("berita", {})
    allow_photo = bc.get("foto_dari", [".go.id", "wikimedia.org"])
    if bc.get("foto_media"):
        allow_photo = None  # semua sumber tepercaya (risiko hak cipta ditanggung pemilik akun)
    state.work("riset", "Mencari berita terkini dari media tepercaya...")
    if topic:
        cfg = {**cfg, "berita": {**bc, "kueri": {"x": [topic]}}}
        items = search(cfg, "x", hours=72)
    else:
        items = search(cfg, pillar_id) or search(cfg, None)
    used = set(state.d.get("news_used", []))
    groups = [g for g in cluster(items) if not any(_norm(x["title"])[:60] in used for x in g)]
    # utamakan cerita yang diberitakan banyak media & yang punya sumber pemerintah
    groups.sort(key=lambda g: (len(g), any(x["domain"].endswith(".go.id") for x in g), max(x["published"] for x in g)), reverse=True)
    cadangan = None
    for g in groups[:5]:
        arts = []
        for it in g[:3]:
            url = decode(it["gn"])
            if not url:
                continue
            try:
                a = read_article(url)
            except Exception as e:
                print("artikel gagal:", url, e)
                continue
            if len(a["text"]) < 300 and len(a["description"]) < 80:
                continue
            a.update(source=it["source"], domain=_domain(url) or it["domain"], published=it["published"])
            arts.append(a)
            time.sleep(1)
        if not arts:
            continue
        cands = []
        for a in arts:
            if allow_photo is None or _match(a["domain"], allow_photo):
                cands += [{**c, "source": a["source"]} for c in a["images"]]
        photos = fetch_images(cands, limit=bc.get("maks_foto", 6))
        if not photos and cadangan is None:  # simpan dulu, coba cari cerita lain yang punya foto
            cadangan = (g, arts, photos)
            continue
        if not photos:
            continue
        return _pakai(state, g, arts, photos)
    if cadangan:
        return _pakai(state, *cadangan)
    state.done("riset", "Belum ada berita baru yang cocok")
    return None, None


def verify(cfg, state, data, articles):
    """Kaka Agus: cocokkan rangkuman dengan sumber; buang fakta yang tidak ada di sumber."""
    state.work("qc", "Mencocokkan rangkuman berita dengan sumber...")
    src = "\n\n".join(f"[{a['source']}] {a['title']}\n{a['description']}\n{a['text'][:2000]}" for a in articles)
    try:
        res = llm.ask("Periksa rangkuman berita JSON ini terhadap SUMBER. Hapus/ubah setiap angka, nama, tanggal, atau klaim yang "
                      "tidak ada di sumber; pastikan tidak menyalin kalimat panjang dari sumber dan netral. "
                      "Balas JSON {\"issues\": [...], \"risk\": \"rendah|sedang|tinggi\", \"content\": <JSON rangkuman yang sudah diperbaiki, struktur sama>}\n\n"
                      f"RANGKUMAN:\n{data}\n\nSUMBER:\n{src}",
                      "Anda pemeriksa fakta redaksi yang teliti.", as_json=True)
        fixed = res.get("content") if isinstance(res.get("content"), dict) and res["content"].get("judul") else data
        fixed["_qc"] = {"issues": res.get("issues", []), "risk": res.get("risk", "rendah")}
    except Exception as e:
        fixed = data
        fixed["_qc"] = {"issues": [f"QC gagal: {e}"], "risk": "sedang"}
    state.done("qc", f"Cek berita selesai — risiko {fixed['_qc']['risk']}")
    return fixed
