"""
Galaxy Gamez - Posting Engine (main.py)
Runs every 3 hours via GitHub Actions.

BUG FIX vs old version:
  - OLD: random.shuffle(unposted)[:3]  -> random order, 3 at a time,
         and a post was only marked "posted" if ALL channels succeeded,
         so one failed channel caused a full repeat to everyone.
  - NEW: strict feed order (oldest -> newest), ONE post per channel per
         cycle, and "posted" is tracked PER CHANNEL, so a single failed
         channel never causes a repeat on channels that already got it.
"""

import time
from datetime import datetime, timedelta
import feedparser

from config import (
    DEFAULT_CHANNEL_IDS, DEFAULT_BLOG_FEED_URL, POSTS_PER_CYCLE,
    DELAY_BETWEEN_CHANNELS, DEFAULT_INTERVAL_HOURS,
)
from storage import (
    load_state, load_stats, save_stats, load_users, save_users,
    get_user, now_iso,
)
from telegram_api import send_with_retry
from caption import build_caption, extract_image


def get_feed_entries(feed_url):
    """Returns entries OLDEST FIRST (strict chronological order)."""
    parsed = feedparser.parse(feed_url)
    entries = list(parsed.entries)
    entries.reverse()  # blogger feeds come newest-first by default
    return entries


def next_unposted(entries, posted_links):
    for entry in entries:
        if entry.link not in posted_links:
            return entry
    return None  # feed fully exhausted


def _legacy_posted_links():
    """One-time migration: pull history from the old posted_posts.json
    (shared across all 6 channels in the old system) so switching over
    doesn't cause a flood of reposts."""
    try:
        import json
        with open("posted_posts.json", "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def ensure_default_admin(users):
    """Make sure Josh's own 6 channels exist in the new multi-user system."""
    admin_id = "__admin__"
    if admin_id not in users:
        legacy = _legacy_posted_links()
        users[admin_id] = {
            "is_admin": True,
            "banned": False,
            "strikes": 0,
            "onboarding": {"step": None, "pending_channel_id": None},
            "channels": [
                {
                    "channel_id": cid,
                    "title": "Galaxy Gamez",
                    "blog_feed_url": DEFAULT_BLOG_FEED_URL,
                    "paused": False,
                    "posted": list(legacy),  # seeded from old shared history
                    "interval_hours": DEFAULT_INTERVAL_HOURS,
                    "last_posted_at": None,
                }
                for cid in DEFAULT_CHANNEL_IDS
            ],
        }
    return users


def run_posting_cycle(manual=False):
    state = load_state()
    if state.get("paused") and not manual:
        return "Skipped - global posting is paused."

    users = load_users()
    users = ensure_default_admin(users)
    stats = load_stats()

    feed_cache = {}  # blog_feed_url -> entries, avoid re-fetching same feed per cycle
    results = []

    for user_id, u in users.items():
        if u.get("banned"):
            continue
        for ch in u.get("channels", []):
            if ch.get("paused"):
                continue

            # Per-channel schedule check - skip if not due yet
            interval_hours = ch.get("interval_hours", DEFAULT_INTERVAL_HOURS)
            last_posted_at = ch.get("last_posted_at")
            if last_posted_at and not manual:
                elapsed = datetime.utcnow() - datetime.fromisoformat(last_posted_at)
                if elapsed < timedelta(hours=interval_hours):
                    continue  # not due yet on this channel's own schedule

            feed_url = ch["blog_feed_url"]
            if feed_url not in feed_cache:
                feed_cache[feed_url] = get_feed_entries(feed_url)
            entries = feed_cache[feed_url]

            posted_links = ch.setdefault("posted", [])
            posted_any = False

            for _ in range(POSTS_PER_CYCLE):
                entry = next_unposted(entries, posted_links)

                if entry is None:
                    # Feed fully exhausted for this channel - loop back to start
                    posted_links.clear()
                    entry = next_unposted(entries, posted_links)

                if entry is None:
                    results.append(f"{ch['channel_id']}: no posts in feed")
                    break

                image_url = extract_image(entry)
                caption = build_caption(entry)
                success, message, _msg_id = send_with_retry(ch["channel_id"], image_url, caption)

                stats["posts_sent"] = stats.get("posts_sent", 0) + 1
                if success:
                    stats["success"] = stats.get("success", 0) + 1
                    posted_links.append(entry.link)  # ONLY mark posted for THIS channel
                    results.append(f"{ch['channel_id']}: OK - {entry.title}")
                    posted_any = True
                else:
                    stats["failed"] = stats.get("failed", 0) + 1
                    results.append(f"{ch['channel_id']}: FAILED - {message}")
                    break  # stop this channel's batch on failure, don't force through retries endlessly

                time.sleep(DELAY_BETWEEN_CHANNELS)

            if posted_any:
                ch["last_posted_at"] = now_iso()

    save_users(users)
    save_stats(stats)

    log_line = f"[{now_iso()}] " + " | ".join(results) if results else f"[{now_iso()}] nothing to post"
    with open("last_run_log.txt", "a") as f:
        f.write(log_line + "\n")

    return log_line


if __name__ == "__main__":
    print(run_posting_cycle())
