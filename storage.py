"""
Galaxy Gamez - Storage Layer
All persistence is plain JSON files, committed back to the repo by
GitHub Actions after every run (no external database).
"""

import json
import os
from datetime import date, datetime

from config import USERS_FILE, BROADCASTS_FILE, STATE_FILE, STATS_FILE


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ---------------- STATE (pause flag, telegram update offset) ----------------

def load_state():
    return load_json(STATE_FILE, {"paused": False, "last_update_id": 0})


def save_state(state):
    save_json(STATE_FILE, state)


# ---------------- STATS ----------------

def today_str():
    return date.today().isoformat()


def load_stats():
    stats = load_json(STATS_FILE, {})
    if stats.get("date") != today_str():
        stats = {"date": today_str(), "posts_sent": 0, "success": 0, "failed": 0}
    return stats


def save_stats(stats):
    save_json(STATS_FILE, stats)


# ---------------- USERS ----------------
# {
#   "<telegram_user_id>": {
#     "is_admin": bool,
#     "banned": bool,
#     "strikes": int,
#     "onboarding": {"step": null | "awaiting_channel" | "awaiting_blog", "pending_channel_id": ...},
#     "channels": [
#        {"channel_id": -100..., "title": "...", "blog_feed_url": "...",
#         "paused": false, "posted": ["link1", "link2", ...]}
#     ]
#   }
# }

def load_users():
    return load_json(USERS_FILE, {})


def save_users(users):
    save_json(USERS_FILE, users)


def get_user(users, user_id):
    user_id = str(user_id)
    if user_id not in users:
        users[user_id] = {
            "is_admin": False,
            "banned": False,
            "strikes": 0,
            "terms_accepted": False,
            "gemz_balance": 0,
            "extra_channel_slots": False,
            "onboarding": {"step": None, "pending_channel_id": None},
            "channels": [],
        }
    return users[user_id]


def all_active_channels(users):
    """Returns flat list of (user_id, channel_dict) for every channel that
    should be posted to this cycle (not banned, not paused)."""
    result = []
    for user_id, u in users.items():
        if u.get("banned"):
            continue
        for ch in u.get("channels", []):
            if ch.get("paused"):
                continue
            result.append((user_id, ch))
    return result


# ---------------- BROADCASTS (for delete-detection / strike system) ----------------
# [{"channel_id": ..., "user_id": ..., "message_id": ..., "sent_at": iso, "checked": bool}]

def load_broadcasts():
    return load_json(BROADCASTS_FILE, [])


def save_broadcasts(data):
    save_json(BROADCASTS_FILE, data)


def now_iso():
    return datetime.utcnow().isoformat()


# ---------------- REDEEM CODES ----------------
# [{"code": "ABC123", "user_id": "...", "amount": 500, "used": false, "created_at": iso}]
REDEEM_CODES_FILE = "redeem_codes.json"


def load_redeem_codes():
    return load_json(REDEEM_CODES_FILE, [])


def save_redeem_codes(data):
    save_json(REDEEM_CODES_FILE, data)
