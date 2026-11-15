"""Otak AI gratis: Google Gemini (free tier) dengan cadangan Groq (free tier)."""
import json
import re
import time

import requests

from .core import env


_MODELS = None


def gemini_models():
    """Daftar model Gemini 'flash' (terbaik dulu). GEMINI_MODEL bila diisi selalu dicoba pertama."""
    global _MODELS
    if _MODELS:
        return _MODELS
    names = []
    try:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                         params={"key": env("GEMINI_API_KEY"), "pageSize": 200}, timeout=30)
        for m in r.json().get("models", []):
            n = m["name"].split("/")[-1]
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            if "flash" not in n or any(x in n for x in ("image", "tts", "audio", "live", "embed", "thinking", "exp")):
                continue
            names.append(n)
    except Exception as e:
        print("Gagal membaca daftar model Gemini:", e)

    def rank(n):
        ver = re.findall(r"(\d+(?:\.\d+)?)", n)
        return (float(ver[0]) if ver else 0, "lite" not in n, "preview" not in n)
    names = sorted(set(names), key=rank, reverse=True)
    # cadangan: versi terbaru, lalu versi lite (biasanya lebih longgar saat server penuh)
    ordered = [n for n in names if "lite" not in n][:2] + [n for n in names if "lite" in n][:2]
    if env("GEMINI_MODEL"):
        ordered.insert(0, env("GEMINI_MODEL"))
    _MODELS = list(dict.fromkeys(ordered)) or ["gemini-flash-latest", "gemini-flash-lite-latest"]
    print("Urutan model Gemini:", ", ".join(_MODELS))
    return _MODELS


def gemini_model() -> str:
    return gemini_models()[0]


def _gemini(prompt: str, system: str, as_json: bool) -> str:
    key = env("GEMINI_API_KEY")
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.8},
    }
    if as_json:
        body["generationConfig"]["responseMimeType"] = "application/json"
    last = None
    for model in gemini_models():  # server penuh / timeout → coba model berikutnya
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        try:
            r = requests.post(url, json=body, timeout=60)
            if r.status_code in (429, 500, 503, 504):
                last = f"{model}: {r.status_code} {r.text[:120]}"
                print("Gemini sibuk, coba model lain →", last)
                continue
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except requests.exceptions.Timeout:
            last = f"{model}: timeout"
            print("Gemini timeout, coba model lain →", model)
    raise RuntimeError(f"Semua model Gemini sibuk: {last}")


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
