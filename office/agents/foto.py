"""Mas Desain (asisten foto) — OPSIONAL: membuat foto cover baru Cicilia dengan Gemini Image.

Mode gratis (default): tidak dipakai; cover memakai potongan foto di assets/influencer/.
Mode Gemini: isi secret IMAGE_MODE=gemini. Model gambar Gemini TIDAK termasuk kuota gratis,
jadi aktifkan billing di Google AI Studio (± US$0,04 ≈ Rp650 per gambar → ± Rp20 ribu/bulan untuk 1 cover/hari).
Jika gagal (kuota/billing), otomatis kembali ke mode gratis.
"""
import base64
import io

import requests
from PIL import Image

from ..core import ROOT, env

REF = ROOT / "assets" / "influencer" / "referensi_wajah.jpg"


def scene_prompt(cfg, content):
    inf = cfg.get("influencer", {})
    return (
        f"Foto editorial realistis, rasio 4:5 potret. Wanita pada foto referensi ({inf.get('name', 'Cicilia')}) "
        f"dengan wajah, rambut panjang cokelat, dan seragam PDH ASN khaki yang sama, termasuk badge 'ASN Go Digital' di lengan kiri. "
        f"{inf.get('style_guard', '')} "
        f"Adegan sesuai topik: \"{content.get('hook', '')}\". "
        "Pencahayaan studio lembut bernuansa biru navy dengan aksen emas, latar kantor pemerintahan Indonesia yang blur, "
        "subjek di sisi kanan setinggi pinggang, menatap kamera, ramah. Sisakan 35% bagian atas dan sisi kiri lapang untuk judul. "
        "Tanpa teks, tanpa logo lain, tanpa tokoh nyata, tanpa lambang negara."
    )


def generate_cover(cfg, state, content):
    if env("IMAGE_MODE").lower() != "gemini" or not env("GEMINI_API_KEY") or not REF.exists():
        return None
    state.work("desain", "Memotret pose baru Cicilia (Gemini Image)...")
    model = env("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={env('GEMINI_API_KEY')}"
    body = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(REF.read_bytes()).decode()}},
            {"text": scene_prompt(cfg, content)},
        ]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "4:5"}},
    }
    try:
        r = requests.post(url, json=body, timeout=180)
        r.raise_for_status()
        for part in r.json()["candidates"][0]["content"]["parts"]:
            data = part.get("inline_data") or part.get("inlineData")
            if data:
                state.done("desain", "Foto cover AI selesai")
                return Image.open(io.BytesIO(base64.b64decode(data["data"])))
    except Exception as e:
        print("Gemini Image gagal, pakai mode gratis:", e)
    state.done("desain", "Pakai pose dari pustaka (mode gratis)")
    return None
