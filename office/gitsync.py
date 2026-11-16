"""Unggah file media ke repo (GitHub Actions) agar Instagram bisa mengambilnya dari URL publik."""
import os
import subprocess
import time

import requests

from .core import ROOT


def push_media(paths, public_urls):
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    g = ["git", "-C", str(ROOT), "-c", "user.name=kantor-bot", "-c", "user.email=kantor-bot@users.noreply.github.com"]
    subprocess.run(g + ["add", "-f", *paths], check=False)
    if subprocess.run(g + ["diff", "--cached", "--quiet"]).returncode != 0:
        subprocess.run(g + ["commit", "-q", "-m", "kantor: media siap terbit"], check=False)
        for _ in range(3):
            subprocess.run(g + ["pull", "-q", "--rebase", "-X", "theirs"], check=False)
            if subprocess.run(g + ["push", "-q"]).returncode == 0:
                break
            time.sleep(4)
    for url in public_urls[:1]:  # tunggu CDN GitHub siap
        for _ in range(24):
            try:
                if requests.head(url, timeout=10).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(5)
