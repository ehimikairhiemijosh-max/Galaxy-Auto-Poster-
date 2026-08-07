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
    DEFAULT_CHANNEL_IDS, DEFAULT_BLOG_FEED_URL, DEFAULT_INTERVAL_HOURS,
    DEFAULT_POSTS_PER_CYCLE, DELAY_BETWEEN_CHANNELS, DEFAULT_GENERIC_TEMPLATE,
)
from storage import (
    load_state, load_stats, save_stats, load_users, save_users,
    get_user, now_iso,
)
from telegram_api import send_with_retry, send_message
from caption import build_caption, render_caption, extract_image


MAX_FEED_ENTRIES = 1500  # safety cap so a feed with millions of posts can't exhaust memory/time


def get_feed_entries(feed_url):
    """Returns entries OLDEST FIRST (strict chronological order).
    Most single RSS feed pages only return the newest ~10-25 items by
    default. This pulls as many as the platform allows:
      - Blogger: max-results param can be raised directly on the URL
      - WordPress: supports ?paged=N pagination on the /feed/ URL
      - Everything else: takes whatever the feed naturally returns
        (most self-hosted/generic RSS feeds don't support pagination at
        all, so this is already the maximum available)
    Capped at MAX_FEED_ENTRIES total as a safety limit."""
    all_entries = []
    seen_links = set()

    if "blogspot.com" in feed_url or "/feeds/posts/default" in feed_url:
        url = feed_url
        if "max-results" in url:
            import re
            url = re.sub(r"max-results=\d+", f"max-results={MAX_FEED_ENTRIES}", url)
        else:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}max-results={MAX_FEED_ENTRIES}"
        parsed = feedparser.parse(url)
        all_entries = list(parsed.entries)

    elif "/feed" in feed_url:
        # Try WordPress-style pagination: /feed/?paged=2, ?paged=3, ...
        page = 1
        while len(all_entries) < MAX_FEED_ENTRIES:
            sep = "&" if "?" in feed_url else "?"
            page_url = feed_url if page == 1 else f"{feed_url}{sep}paged={page}"
            parsed = feedparser.parse(page_url)
            if not parsed.entries:
                break
            new_ones = [e for e in parsed.entries if e.link not in seen_links]
            if not new_ones:
                break  # site ignored the paged param / looped back to page 1
            for e in new_ones:
                seen_links.add(e.link)
            all_entries.extend(new_ones)
            page += 1
            if page > 60:  # hard stop - ~1500 posts at 25/page
                break
    else:
        parsed = feedparser.parse(feed_url)
        all_entries = list(parsed.entries)

    all_entries = all_entries[:MAX_FEED_ENTRIES]
    all_entries.reverse()  # feeds come newest-first by default
    return all_entries


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
                    "posts_per_cycle": DEFAULT_POSTS_PER_CYCLE,
                    "caption_template": None,  # unused - admin always uses build_caption
                    "last_posted_at": None,
                }
                for cid in DEFAULT_CHANNEL_IDS
            ],
        }
    return users


def run_posting_cycle(manual=False, only_user_id=None, users=None):
    """If `users` is passed in (e.g. from the live bot server), this
    mutates that SAME dict in place and does NOT save/push on its own -
    the caller is responsible for one final save, exactly like every
    other command. This avoids a stale outer copy later overwriting the
    fresh changes made here (that overwrite was the cause of "Post Now"
    reposting/repeating the same entries every time).
    If `users` is None (the standalone GitHub Actions entry point), this
    loads and saves everything itself as before."""
    standalone = users is None

    state = load_state()
    if state.get("paused") and not manual:
        return "Skipped - global posting is paused."

    if standalone:
        users = load_users()
    users = ensure_default_admin(users)
    stats = load_stats()

    feed_cache = {}  # blog_feed_url -> entries, avoid re-fetching same feed per cycle
    results = []

    for user_id, u in users.items():
        if only_user_id is not None and user_id != only_user_id:
            continue
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
            was_first_post_ever = len(posted_links) == 0
            posted_any = False
            posts_per_cycle = ch.get("posts_per_cycle", DEFAULT_POSTS_PER_CYCLE)

            for _ in range(posts_per_cycle):
                entry = next_unposted(entries, posted_links)

                if entry is None:
                    # Feed fully exhausted for this channel - loop back to start
                    posted_links.clear()
                    entry = next_unposted(entries, posted_links)

                if entry is None:
                    results.append(f"{ch['channel_id']}: no posts in feed")
                    break

                image_url = extract_image(entry)
                if user_id == "__admin__":
                    caption = build_caption(entry)
                else:
                    template = ch.get("caption_template") or DEFAULT_GENERIC_TEMPLATE
                    caption = render_caption(entry, template)
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

                if (was_first_post_ever and user_id != "__admin__"
                        and u.get("referred_by") and u.get("referral_completed")
                        and u.get("trial_started_at") is None):
                    u["trial_started_at"] = now_iso()
                    try:
                        send_message(
                            user_id,
                            "🎁 Your 24-hour free trial has started! After it ends, "
                            "you'll get 500 free Gemz to keep going.",
                        )
                    except Exception:
                        pass  # never let a notification failure break the posting cycle

    if standalone:
        save_users(users)
        save_stats(stats)
    else:
        save_stats(stats)  # stats.json has no clobber risk, safe to save immediately

    log_line = f"[{now_iso()}] " + " | ".join(results) if results else f"[{now_iso()}] nothing to post"
    with open("last_run_log.txt", "a") as f:
        f.write(log_line + "\n")

    return log_line


if __name__ == "__main__":
    print(run_posting_cycle())
