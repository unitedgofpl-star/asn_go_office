"""Meta Graph API (gratis): terbitkan carousel ke Instagram Business & Facebook Page."""
import time

import requests

from .core import env

def _base():
    return f"https://graph.facebook.com/{env('GRAPH_VERSION', 'v21.0')}"


def _token():
    t = env("META_PAGE_TOKEN")
    if not t:
        raise RuntimeError("META_PAGE_TOKEN belum diisi di GitHub Secrets.")
    return t


def _check(r):
    js = r.json()
    if "error" in js:
        raise RuntimeError(f"Meta API: {js['error'].get('message')}")
    return js


# ---------------- Instagram ----------------
def ig_publish_carousel(image_urls, caption: str) -> str:
    ig = env("IG_USER_ID")
    tok = _token()
    if len(image_urls) == 1:
        c = _check(requests.post(f"{_base()}/{ig}/media", data={"image_url": image_urls[0], "caption": caption, "access_token": tok}, timeout=60))
        creation = c["id"]
    else:
        children = []
        for url in image_urls[:10]:
            c = _check(requests.post(f"{_base()}/{ig}/media", data={"image_url": url, "is_carousel_item": "true", "access_token": tok}, timeout=60))
            children.append(c["id"])
        c = _check(requests.post(f"{_base()}/{ig}/media", data={
            "media_type": "CAROUSEL", "children": ",".join(children), "caption": caption, "access_token": tok}, timeout=60))
        creation = c["id"]
    # tunggu container siap
    for _ in range(20):
        st = _check(requests.get(f"{_base()}/{creation}", params={"fields": "status_code", "access_token": tok}, timeout=30))
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError("Instagram menolak media (cek ukuran/format gambar).")
        time.sleep(5)
    pub = _check(requests.post(f"{_base()}/{ig}/media_publish", data={"creation_id": creation, "access_token": tok}, timeout=60))
    link = _check(requests.get(f"{_base()}/{pub['id']}", params={"fields": "permalink", "access_token": tok}, timeout=30))
    return link.get("permalink", pub["id"])


def ig_recent_media(limit=20):
    ig, tok = env("IG_USER_ID"), _token()
    js = _check(requests.get(f"{_base()}/{ig}/media", params={
        "fields": "id,caption,like_count,comments_count,timestamp,permalink,media_type",
        "limit": limit, "access_token": tok}, timeout=30))
    items = js.get("data", [])
    for it in items:  # reach & saved (butuh izin instagram_manage_insights)
        try:
            ins = _check(requests.get(f"{_base()}/{it['id']}/insights", params={
                "metric": "reach,saved,shares", "access_token": tok}, timeout=30))
            for m in ins.get("data", []):
                it[m["name"]] = m["values"][0]["value"]
        except Exception:
            pass
    return items


def ig_profile():
    ig, tok = env("IG_USER_ID"), _token()
    return _check(requests.get(f"{_base()}/{ig}", params={"fields": "username,followers_count,media_count", "access_token": tok}, timeout=30))


# ---------------- Facebook Page ----------------
def fb_publish_album(image_paths, message: str) -> str:
    page, tok = env("FB_PAGE_ID"), _token()
    ids = []
    for p in image_paths[:10]:
        with open(p, "rb") as f:
            r = _check(requests.post(f"{_base()}/{page}/photos", data={"published": "false", "access_token": tok},
                                     files={"source": f}, timeout=120))
            ids.append(r["id"])
    data = {"message": message, "access_token": tok}
    for i, mid in enumerate(ids):
        data[f"attached_media[{i}]"] = '{"media_fbid":"%s"}' % mid
    post = _check(requests.post(f"{_base()}/{page}/feed", data=data, timeout=60))
    return f"https://facebook.com/{post['id']}"
