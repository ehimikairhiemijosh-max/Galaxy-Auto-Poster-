"""
Galaxy Gamez - Git Sync Layer
Both the Render command server AND the GitHub Actions posting job read/write
the same JSON files. Since there's no separate database, git itself is the
source of truth. This module keeps the local working copy in sync before
every read and pushes after every write, with a retry-on-conflict pattern.
"""

import os
import subprocess
import time

from config import GITHUB_TOKEN, GITHUB_REPOSITORY

REPO_DIR = "/tmp/repo" if os.environ.get("RENDER") else "."


def _run(cmd, cwd=None):
    result = subprocess.run(cmd, cwd=cwd or REPO_DIR, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def ensure_repo():
    """On Render, clone the repo into /tmp on first boot. Locally (GitHub
    Actions), the repo is already checked out, so this is a no-op."""
    if not os.environ.get("RENDER"):
        return
    if os.path.exists(os.path.join(REPO_DIR, ".git")):
        return
    url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPOSITORY}.git"
    subprocess.run(["git", "clone", url, REPO_DIR], capture_output=True, text=True)
    _run(["git", "config", "user.name", "render-bot"])
    _run(["git", "config", "user.email", "render-bot@galaxygamez.local"])


def pull_latest():
    ensure_repo()
    _run(["git", "fetch", "origin", "main"])
    _run(["git", "reset", "--hard", "origin/main"])


def push_changes(message, files):
    """files: list of filenames (relative to repo root) to commit. Retries
    once on conflict by pulling and re-applying (git handles this fine since
    each JSON write is a full-file overwrite from load->modify->save)."""
    for attempt in range(2):
        _run(["git", "add"] + files)
        code, out, err = _run(["git", "commit", "-m", message])
        if "nothing to commit" in (out + err):
            return True
        code, out, err = _run(["git", "push", "origin", "main"])
        if code == 0:
            return True
        # push rejected - pull latest and retry once
        pull_latest()
        time.sleep(1)
    return False
