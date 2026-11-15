"""Mbak Humas — menerbitkan draft yang sudah disetujui ke Instagram & Facebook Page."""
from .. import meta, telegram
from ..core import ROOT, env, now_wit


def caption_of(d):
    c = d["content"]
    tags = " ".join(c.get("hashtags", []))
    return f"{c.get('caption', '')}\n\n{tags}".strip()


def public_urls(paths):
    """URL publik gambar dari repo GitHub publik (dibutuhkan Instagram API)."""
    repo = env("GITHUB_REPOSITORY")
    branch = env("GITHUB_REF_NAME", "main")
    base = env("PUBLIC_BASE_URL") or f"https://raw.githubusercontent.com/{repo}/{branch}"
    return [f"{base.rstrip('/')}/{p}" for p in paths]


def publish(cfg, state, draft_id):
    d = state.d["drafts"][draft_id]
    state.work("humas", f"Menerbitkan #{draft_id} ke IG & FB...")
    cap = caption_of(d)
    result, errors = {}, []
    if env("IG_USER_ID"):
        try:
            result["ig"] = meta.ig_publish_carousel(public_urls(d["images"]), cap)
        except Exception as e:
            errors.append(f"IG: {e}")
    if env("FB_PAGE_ID"):
        try:
            result["fb"] = meta.fb_publish_album([str(ROOT / p) for p in d["images"]], cap)
        except Exception as e:
            errors.append(f"FB: {e}")
    d["published"] = result
    d["published_at"] = now_wit().isoformat(timespec="minutes")
    if result:
        d["status"] = "published"
        state.d["stats"]["published"] += 1
    else:
        d["status"] = "failed"
    d["errors"] = errors
    msg = f"📣 <b>#{draft_id} {('terbit' if result else 'GAGAL terbit')}</b>\n"
    msg += "\n".join(f"• {k.upper()}: {v}" for k, v in result.items())
    if errors:
        msg += "\n⚠️ " + "\n⚠️ ".join(errors)
    telegram.send(msg)
    state.done("humas", f"#{draft_id} → {', '.join(result) or 'gagal'}")


def publish_due(cfg, state):
    """Terbitkan semua draft 'approved' yang jadwalnya sudah lewat."""
    now = now_wit().isoformat(timespec="minutes")
    for did, d in list(state.d["drafts"].items()):
        if d.get("status") == "approved" and d.get("scheduled_at", "") <= now:
            publish(cfg, state, did)
