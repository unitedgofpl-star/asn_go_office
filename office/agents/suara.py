"""Studio suara: narasi Cicilia (suara perempuan) + musik latar buatan sendiri (bebas royalti) + perakit video.

• Suara  : Microsoft Edge TTS "id-ID-GadisNeural" (gratis, tanpa API key) → cadangan Google TTS (gTTS).
• Musik  : disintesis dengan numpy (piano elektrik lo-fi, bass, kick, hi-hat). Nada, tempo & pola acak per video,
           jadi selalu unik dan 100% bebas royalti. Bila ada file MP3 di assets/music/, file itu yang dipakai.
• Video  : frame 9:16 + zoom lembut + transisi bervariasi; durasi tiap frame mengikuti panjang narasinya.
"""
import asyncio
import math
import random
import re
import subprocess
import tempfile
import wave
from pathlib import Path

from ..core import ROOT
from .tiktok import _ffmpeg

MUSIC_DIR = ROOT / "assets" / "music"
TRANSITIONS = ["fade", "slideleft", "smoothup", "circleopen", "wipeleft", "slideup", "radial", "smoothleft"]

# ------------------------------------------------------------------ teks → ucapan
SINGKATAN = {"ASN": "A S N", "PNS": "P N S", "PPPK": "P P P K", "SPBE": "S P B E", "BKN": "B K N", "OPD": "O P D", "AI": "A I",
             "SPJ": "S P J", "TTE": "T T E", "BSrE": "B S R E", "WIT": "W I T", "APBDes": "A P B Des", "RKPDes": "R K P Des",
             "RPJMDes": "R P J M Des", "SK": "S K", "SKP": "S K P", "IG": "I G", "FB": "F B", "WA": "W A", "PDF": "P D F",
             "KemenPANRB": "Kemen PAN R B", "BUMDes": "Bum Des", "SIPD": "S I P D", "Perdes": "Per Des", "PMK": "P M K"}


def ucapan(text):
    t = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️#*_`>|•]", " ", str(text))
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"Rp\s?([\d.]+)\.000\b", lambda m: f"{m.group(1).replace('.', '')} ribu rupiah", t)
    t = re.sub(r"Rp\s?([\d.]+)", lambda m: f"{m.group(1).replace('.', '')} rupiah", t)
    for k, v in SINGKATAN.items():
        t = re.sub(rf"\b{k}\b", v, t)
    t = t.replace("/", " atau ").replace("&", " dan ").replace("%", " persen")
    return re.sub(r"\s+", " ", t).strip()


def _edge(text, out, cfg):
    import edge_tts
    s = cfg.get("suara", {})

    async def run():
        c = edge_tts.Communicate(text, s.get("voice", "id-ID-GadisNeural"), rate=s.get("rate", "+6%"), pitch=s.get("pitch", "+12Hz"))
        await c.save(str(out))
    asyncio.run(run())


def _gtts(text, out, cfg):
    from gtts import gTTS
    gTTS(text, lang="id").save(str(out))


def tts(cfg, text, out):
    """Buat MP3 narasi. Kembalikan durasi (detik) atau 0 bila gagal."""
    text = ucapan(text)
    if not text:
        return 0
    for fn in (_edge, _gtts):
        try:
            fn(text, out, cfg)
            d = duration(out)
            if d > 0.3:
                return d
        except Exception as e:
            print(f"TTS {fn.__name__} gagal:", e)
    return 0


def duration(path):
    r = subprocess.run([_ffmpeg(), "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0


# ------------------------------------------------------------------ musik bebas royalti
NOTE = {"C": 261.63, "D": 293.66, "E": 329.63, "F": 349.23, "G": 392.0, "A": 440.0}
PROG = {"ceria": [0, 7, 9, 5], "semangat": [0, 5, 9, 7], "tenang": [9, 5, 0, 7], "sendu": [9, 4, 5, 0]}
MOOD_MUSIC = {"ceria": "ceria", "semangat": "semangat", "terkejut": "semangat", "cemberut": "sendu", "tegas": "semangat",
              "sedih": "sendu", "sayang": "ceria", "tenang": "tenang", "menjelaskan": "tenang"}


def synth_music(path, seconds, mood="tenang", seed=0):
    import numpy as np
    rnd = random.Random(seed)
    sr = 44100
    style = MOOD_MUSIC.get(mood, "tenang")
    bpm = {"ceria": rnd.randint(96, 108), "semangat": rnd.randint(104, 118), "tenang": rnd.randint(78, 88), "sendu": rnd.randint(70, 80)}[style]
    root = NOTE[rnd.choice(list(NOTE))] / 2
    beat = 60 / bpm
    n = int(sr * (seconds + 1))
    out = np.zeros((n, 2))
    tt = np.arange(n) / sr

    def semis(f, s):
        return f * 2 ** (s / 12)

    def add(sig, start, pan=0.0, gain=1.0):
        i = int(start * sr)
        if i >= n:
            return
        sig = sig[: n - i] * gain
        out[i:i + len(sig), 0] += sig * (1 - pan) * .5 + sig * .5 * (1 - abs(pan))
        out[i:i + len(sig), 1] += sig * (1 + pan) * .5 + sig * .5 * (1 - abs(pan))

    def epiano(f, dur):
        t = np.arange(int(sr * dur)) / sr
        env = np.exp(-t * 2.2) * (1 - np.exp(-t * 60))
        s = (np.sin(2 * np.pi * f * t) + .45 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 4) + .2 * np.sin(2 * np.pi * 3.01 * f * t) * np.exp(-t * 6))
        return s * env * (1 + .15 * np.sin(2 * np.pi * 5 * t))

    bar = beat * 4
    prog = PROG[style]
    minor = {9, 4}
    b = 0.0
    k = 0
    while b < seconds:
        deg = prog[k % 4]
        f0 = semis(root * 2, deg)
        third = 3 if deg in minor else 4
        for s_, g in ((0, .8), (third, .6), (7, .6), (11 if style != "sendu" else 10, .35)):
            add(epiano(semis(f0, s_), bar * 1.05), b, pan=rnd.uniform(-.4, .4), gain=.09 * g)
        # bass
        bt = np.arange(int(sr * bar)) / sr
        bass = np.sin(2 * np.pi * semis(root, deg) * bt) * np.exp(-bt * 1.2) * (1 - np.exp(-bt * 40))
        add(bass, b, gain=.16)
        # drum lo-fi
        for q in range(4):
            tq = b + q * beat
            if q in (0, 2) or (style == "semangat" and q == 3):
                kt = np.arange(int(sr * .35)) / sr
                add(np.sin(2 * np.pi * (50 + 90 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 9), tq, gain=.32)
            if q in (1, 3) and style != "sendu":
                st = np.arange(int(sr * .18)) / sr
                add(np.random.default_rng(int(tq * 1000)).normal(0, 1, len(st)) * np.exp(-st * 25), tq, gain=.05)
            for h in (0, .5):
                ht = np.arange(int(sr * .05)) / sr
                add(np.random.default_rng(int(tq * 977 + h * 13)).normal(0, 1, len(ht)) * np.exp(-ht * 90), tq + h * beat,
                    pan=.3, gain=.025 if style != "sendu" else .012)
        b += bar
        k += 1
    # desis piringan hitam tipis (low-pass lo-fi diterapkan ffmpeg saat mixing)
    out += np.random.default_rng(seed).normal(0, .003, out.shape)
    fade = int(sr * 1.5)
    out[:int(sr * .5)] *= np.linspace(0, 1, int(sr * .5))[:, None]
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    out = out / max(1e-6, np.abs(out).max()) * .8
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((out * 32767).astype("<i2").tobytes())
    return path


def music_track(cfg, seconds, mood, seed, tmp):
    files = sorted(MUSIC_DIR.glob("*.mp3")) if MUSIC_DIR.exists() else []
    if files:
        return random.Random(seed).choice(files)
    return synth_music(Path(tmp) / "musik.wav", seconds, mood, seed)


# ------------------------------------------------------------------ perakit video
def compose(cfg, frames, narr, out, seed=0, mood="tenang", min_dur=2.8, xf=0.45):
    """frames: list PIL 1080x1920; narr: list teks narasi per frame (boleh ''). Kembalikan (path, durasi)."""
    s = cfg.get("suara", {})
    rnd = random.Random(seed)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    voice_on = s.get("aktif", True)
    vdur = []
    for i, txt in enumerate(narr):
        d = tts(cfg, txt, tmp / f"v{i:02d}.mp3") if (voice_on and txt) else 0
        vdur.append(d)
    durs = [max(min_dur, d + 0.7) for d in vdur]
    total = sum(durs) - xf * (len(frames) - 1)
    for i, fr in enumerate(frames):
        fr.convert("RGB").save(tmp / f"f{i:02d}.jpg", quality=92)

    cmd = [_ffmpeg(), "-y", "-loglevel", "error"]
    for i in range(len(frames)):
        cmd += ["-i", str(tmp / f"f{i:02d}.jpg")]
    nf = len(frames)
    parts = []
    for i, dur in enumerate(durs):
        z = "min(zoom+0.0008,1.12)" if rnd.random() < .7 else "if(eq(on,0),1.12,max(zoom-0.0008,1.0))"
        parts.append(f"[{i}:v]scale=1296:2304,zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                     f"d={int(dur * 30)}:s=1080x1920:fps=30,setsar=1,format=yuv420p[v{i}]")
    last, off = "v0", 0.0
    starts = [0.0]
    for i in range(1, nf):
        off += durs[i - 1] - xf
        starts.append(off)
        parts.append(f"[{last}][v{i}]xfade=transition={rnd.choice(TRANSITIONS)}:duration={xf}:offset={off:.2f}[x{i}]")
        last = f"x{i}"

    # audio: narasi tiap frame diletakkan di awal frame-nya + musik latar
    idx = nf
    alabels = []
    for i, d in enumerate(vdur):
        if d > 0:
            cmd += ["-i", str(tmp / f"v{i:02d}.mp3")]
            ms = int((starts[i] + 0.3) * 1000)
            parts.append(f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo,adelay={ms}|{ms},volume=1.6[n{i}]")
            alabels.append(f"[n{i}]")
            idx += 1
    if s.get("musik", True):
        mus = music_track(cfg, total, mood, seed, tmp)
        cmd += ["-stream_loop", "-1", "-i", str(mus)]
        vol = s.get("volume_musik", 0.16) if alabels else 0.45
        parts.append(f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo,atrim=0:{total:.2f},"
                     f"lowpass=f=3800,afade=t=out:st={max(0, total - 1.5):.2f}:d=1.5,volume={vol}[m]")
        alabels.append("[m]")
        idx += 1
    if alabels:
        parts.append(f"{''.join(alabels)}amix=inputs={len(alabels)}:normalize=0:duration=longest,atrim=0:{total:.2f},"
                     f"alimiter=limit=0.95[a]")
        amap = "[a]"
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        amap = f"{idx}:a"
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{last}]", "-map", amap, "-t", f"{total:.2f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    print(f"Video {total:.1f} dtk • narasi {sum(1 for d in vdur if d)}/{nf} frame • musik {'ya' if s.get('musik', True) else 'tidak'}")
    return out, total


# ------------------------------------------------------------------ suara khas Cicilia (kloning nada suara)
# Narasi dibuat dulu dengan suara "Gadis", lalu warna suaranya diubah menjadi suara Cicilia dari rekaman referensi
# memakai OpenVoice V2 (lisensi MIT, boleh komersial, jalan di CPU). Bila gagal → tetap pakai suara Gadis.
import os
import subprocess as _sp
import sys

REF_SUARA = ROOT / "assets" / "influencer" / "suara" / "cicilia_referensi.wav"
VOICE_DIR = Path(os.environ.get("ASN_VOICE_CACHE", Path.home() / ".cache" / "asn_voice"))
HF = "https://huggingface.co/myshell-ai/OpenVoiceV2/resolve/main/converter/"
_VC = {}


def _siapkan_openvoice():
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    repo = VOICE_DIR / "OpenVoice"
    if not (repo / "openvoice" / "models.py").exists():
        _sp.run(["git", "clone", "--depth", "1", "https://github.com/myshell-ai/OpenVoice", str(repo)], check=True)
    try:
        import torch  # noqa
        import librosa  # noqa
        import soundfile  # noqa
    except ImportError:
        _sp.run([sys.executable, "-m", "pip", "install", "-q", "torch", "--index-url", "https://download.pytorch.org/whl/cpu"], check=True)
        _sp.run([sys.executable, "-m", "pip", "install", "-q", "librosa", "soundfile"], check=True)
    import importlib
    importlib.invalidate_caches()
    ck = VOICE_DIR / "converter"
    ck.mkdir(exist_ok=True)
    import requests
    for f in ("config.json", "checkpoint.pth"):
        if not (ck / f).exists() or (ck / f).stat().st_size < 100:
            r = requests.get(HF + f, timeout=300)
            r.raise_for_status()
            (ck / f).write_bytes(r.content)
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    return ck


def _converter():
    if "m" in _VC:
        return _VC["m"]
    ck = _siapkan_openvoice()
    import torch
    from openvoice import utils
    from openvoice.models import SynthesizerTrn
    hps = utils.get_hparams_from_file(str(ck / "config.json"))
    m = SynthesizerTrn(len(getattr(hps, "symbols", [])), hps.data.filter_length // 2 + 1, n_speakers=hps.data.n_speakers, **hps.model)
    m.load_state_dict(torch.load(ck / "checkpoint.pth", map_location="cpu")["model"], strict=False)
    m.eval()
    _VC["m"] = (m, hps)
    return _VC["m"]


def _spec(path, hps, start=None, end=None):
    import librosa
    import torch
    from openvoice.mel_processing import spectrogram_torch
    a, _ = librosa.load(str(path), sr=hps.data.sampling_rate)
    if start is not None:
        a = a[int(start * hps.data.sampling_rate):int(end * hps.data.sampling_rate)]
    y = torch.FloatTensor(a).unsqueeze(0)
    return spectrogram_torch(y, hps.data.filter_length, hps.data.sampling_rate, hps.data.hop_length, hps.data.win_length, center=False)


def _se(path, m, hps, seg=3.0):
    """Sidik warna suara (speaker embedding) = rata-rata dari potongan ±3 detik."""
    import torch
    total = duration(path)
    gs = []
    t = 0.0
    while t + 1.0 < total:
        sp = _spec(path, hps, t, min(total, t + seg))
        with torch.no_grad():
            gs.append(m.ref_enc(sp.transpose(1, 2)).unsqueeze(-1))
        t += seg
    return torch.stack(gs).mean(0)


def kloning(cfg, src_wav, out_wav):
    """Ubah warna suara narasi menjadi suara Cicilia. Kembalikan True bila berhasil."""
    s = cfg.get("suara", {})
    ref = ROOT / s.get("referensi", str(REF_SUARA.relative_to(ROOT)))
    if not s.get("kloning", True) or not ref.exists():
        return False
    try:
        m, hps = _converter()
        import soundfile as sf
        import torch
        key = ("tgt", str(ref))
        if key not in _VC:
            _VC[key] = _se(ref, m, hps)
        src_se = _se(src_wav, m, hps)
        sp = _spec(src_wav, hps)
        with torch.no_grad():
            audio = m.voice_conversion(sp, torch.LongTensor([sp.size(-1)]), sid_src=src_se, sid_tgt=_VC[key],
                                       tau=float(s.get("tau", 0.3)))[0][0, 0].data.cpu().float().numpy()
        sf.write(str(out_wav), audio, hps.data.sampling_rate)
        return True
    except Exception as e:
        print("Kloning suara Cicilia gagal, pakai suara Gadis:", e)
        return False
