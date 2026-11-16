"""Inti kantor: konfigurasi, state (buku besar kantor), dan log aktivitas karyawan."""
import json
import os
import datetime as dt
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PUBLIC = ROOT / "public"
STATE_FILE = DATA / "state.json"
WIT = dt.timezone(dt.timedelta(hours=9))

# Daftar karyawan AI — dipakai juga oleh kantor 3D (docs/index.html)
AGENTS = {
    "kepala":  "Bapa Yohanis Rumbewas (Kepala Kantor / Manajer Konten)",
    "riset":   "Kaka Maria Kafiar (Analis Riset & Tren)",
    "naskah":  "Kaka Selfina Rumansara (Penulis Konten Senior)",
    "qc":      "Kaka Agustinus Karubaba (Verifikator Fakta & Regulasi)",
    "desain":  "Kaka Elisa Wanggai (Desainer Grafis & Video)",
    "humas":   "Kaka Natalia Ayomi (Humas & Publikasi Medsos)",
    "cuan":    "Kaka Yance Mansoben (Kepala Pemasaran & Penjualan)",
    "analis":  "Kaka Ruth Imbiri (Analis Data & Performa)",
}


def now_wit() -> dt.datetime:
    return dt.datetime.now(WIT)


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class State:
    """State disimpan di data/state.json dan di-commit oleh GitHub Actions."""

    def __init__(self):
        DATA.mkdir(exist_ok=True)
        if STATE_FILE.exists():
            self.d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        else:
            self.d = {}
        self.d.setdefault("tg_offset", 0)
        self.d.setdefault("auto_publish", None)  # None = ikuti config
        self.d.setdefault("drafts", {})
        self.d.setdefault("agents", {k: {"name": v, "status": "idle", "last": "Siap bekerja", "at": ""} for k, v in AGENTS.items()})
        for k, v in AGENTS.items():
            self.d["agents"].setdefault(k, {"name": v, "status": "idle", "last": "Siap bekerja", "at": ""})
            self.d["agents"][k]["name"] = v
        self.d.setdefault("log", [])
        self.d.setdefault("stats", {"published": 0, "drafts": 0})

    # ---- aktivitas karyawan (ditampilkan di kantor 3D) ----
    def work(self, agent: str, msg: str, status: str = "working"):
        t = now_wit().strftime("%Y-%m-%d %H:%M")
        self.d["agents"][agent].update({"status": status, "last": msg, "at": t})
        self.d["log"].insert(0, {"at": t, "agent": agent, "msg": msg})
        self.d["log"] = self.d["log"][:60]
        print(f"[{t}] {AGENTS[agent]}: {msg}")

    def done(self, agent: str, msg: str):
        self.work(agent, msg, status="idle")

    # ---- draft ----
    def new_draft_id(self) -> str:
        base = now_wit().strftime("%m%d%H%M")
        did, i = base, 1
        while did in self.d["drafts"]:
            did, i = f"{base}{i}", i + 1
        return did

    def save(self):
        self.d["updated"] = now_wit().isoformat(timespec="minutes")
        STATE_FILE.write_text(json.dumps(self.d, ensure_ascii=False, indent=1), encoding="utf-8")

    def auto_publish(self, cfg) -> bool:
        if self.d["auto_publish"] is None:
            return not cfg.get("require_approval", True)
        return bool(self.d["auto_publish"])
