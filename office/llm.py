"""Otak AI gratis: Google Gemini (free tier) dengan cadangan Groq (free tier)."""
import json
import re
import time

import requests

from .core import env


_MODEL = None


def gemini_model() -> str:
    """Pakai GEMINI_MODEL bila diisi; jika tidak, cari model 'flash' teks terbaru yang tersedia untuk key ini."""
    global _MODEL
    if _MODEL:
        return _MODEL
    if env("GEMINI_MODEL"):
        _MODEL = env("GEMINI_MODEL")
        return _MODEL
    try:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                         params={"key": env("GEMINI_API_KEY"), "pageSize": 200}, timeout=30)
        names = []
        for m in r.json().get("models", []):
            n = m["name"].split("/")[-1]
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            if "flash" not in n or any(x in n for x in ("image", "tts", "audio", "live", "embed", "thinking", "exp")):
                continue
            names.append(n)

        def rank(n):
            ver = re.findall(r"(\d+(?:\.\d+)?)", n)
            v = float(ver[0]) if ver else 0
            return (v, "lite" not in n, "preview" not in n, n.endswith("latest") is False)
        if names:
            _MODEL = sorted(names, key=rank)[-1]
    except Exception as e:
        print("Gagal membaca daftar model Gemini:", e)
    _MODEL = _MODEL or "gemini-flash-latest"
    print("Model Gemini dipakai:", _MODEL)
    return _MODEL


def _gemini(prompt: str, system: str, as_json: bool) -> str:
    key = env("GEMINI_API_KEY")
    model = gemini_model()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.8},
    }
    if as_json:
        body["generationConfig"]["responseMimeType"] = "application/json"
    r = requests.post(url, json=body, timeout=120)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _groq(prompt: str, system: str, as_json: bool) -> str:
    body = {
        "model": env("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "temperature": 0.8,
    }
    if as_json:
        body["response_format"] = {"type": "json_object"}
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {env('GROQ_API_KEY')}"},
        json=body,
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def ask(prompt: str, system: str = "Anda asisten yang membantu.", as_json: bool = False):
    """Coba Gemini dulu, lalu Groq. Kembalikan teks atau dict (jika as_json)."""
    providers = []
    if env("GEMINI_API_KEY"):
        providers.append(_gemini)
    if env("GROQ_API_KEY"):
        providers.append(_groq)
    if not providers:
        raise RuntimeError("Isi GEMINI_API_KEY atau GROQ_API_KEY di GitHub Secrets.")

    last = None
    for fn in providers:
        for attempt in range(3):
            try:
                out = fn(prompt, system, as_json)
                return parse_json(out) if as_json else out.strip()
            except Exception as e:  # rate limit / format error → coba lagi
                last = e
                time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"Semua penyedia AI gagal: {last}")


def parse_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(0))
