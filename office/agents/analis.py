"""Kak Analis — membaca performa IG dan memberi rekomendasi mingguan."""
import json

from .. import llm, meta


def weekly_report(cfg, state):
    state.work("analis", "Menarik data performa Instagram...")
    try:
        prof = meta.ig_profile()
        media = meta.ig_recent_media(15)
    except Exception as e:
        state.done("analis", f"Gagal ambil data: {e}")
        return f"⚠️ Kak Analis gagal mengambil data Meta: {e}"
    rows = [{k: m.get(k) for k in ("timestamp", "like_count", "comments_count", "reach", "saved", "shares")}
            | {"judul": (m.get("caption") or "")[:70]} for m in media]
    prev = state.d.get("last_followers")
    state.d["last_followers"] = prof.get("followers_count")
    growth = "" if prev is None else f" (perubahan sejak laporan lalu: {prof.get('followers_count', 0) - prev:+d})"
    summary = llm.ask(
        "Anda analis media sosial. Buat laporan mingguan singkat (maks 180 kata) dalam Bahasa Indonesia untuk akun "
        f"{cfg['brand']['handle']}. Followers: {prof.get('followers_count')}{growth}. Data 15 postingan terakhir:\n"
        f"{json.dumps(rows, ensure_ascii=False)}\n\n"
        "Isi: 1) 3 postingan terbaik & alasannya, 2) pola (topik/format) yang paling disimpan/dibagikan, "
        "3) 3 rekomendasi konkret minggu depan, 4) 1 ide untuk mendorong penjualan produk lynk.id. Pakai poin-poin.")
    state.done("analis", f"Laporan mingguan selesai — {prof.get('followers_count')} followers")
    return f"📊 <b>Laporan Mingguan {cfg['brand']['handle']}</b>\nFollowers: {prof.get('followers_count')}{growth}\n\n{summary}"
