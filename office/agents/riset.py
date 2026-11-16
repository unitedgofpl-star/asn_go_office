"""Kaka Maria — memantau berita & tren terbaru via Google News RSS (gratis)."""
import random
import urllib.parse

import feedparser


def headlines(cfg, state, n=10):
    state.work("riset", "Memantau berita ASN, desa & AI...")
    items = []
    queries = cfg.get("research_queries", [])
    for q in random.sample(queries, min(4, len(queries))):
        url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(q + " when:7d") + "&hl=id&gl=ID&ceid=ID:id"
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:5]:
                items.append(f"- {e.title}")
        except Exception as ex:
            print("RSS gagal:", ex)
    items = list(dict.fromkeys(items))[:n]
    state.done("riset", f"Menemukan {len(items)} berita tren minggu ini")
    return items
