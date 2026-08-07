"""
Galaxy Gamez - Render Command Server (bot_server.py)
Always-on process replacing the old 5-minute GitHub Actions command check.
Run with: gunicorn bot_server:app --workers 1 --timeout 120
(MUST be --workers 1 - multiple workers would double-poll Telegram and
cause duplicate replies / offset conflicts.)
"""

import os
import threading
import time
import socket

socket.setdefaulttimeout(25)  # global safety net - no single network call can hang forever

os.environ["RENDER"] = "1"

import git_sync
git_sync.ensure_repo()
os.chdir(git_sync.REPO_DIR)

from flask import Flask
from config import BOT_TOKEN, ADMIN_CHAT_ID, API_BASE
from storage import load_state, save_state, load_users, save_users, now_iso
from bot_commands import (
    handle_message, handle_callback, ensure_default_admin,
    check_broadcast_strikes, check_referral_trials,
)

import requests
requests.post(f"{API_BASE}/deleteWebhook", data={"drop_pending_updates": False}, timeout=15)

app = Flask(__name__)
POLL_INTERVAL = 2  # seconds between getUpdates calls - feels instant

_last_alive = {"ts": time.time()}


@app.route("/")
def health():
    return "Galaxy Gamez bot is running.", 200


def poll_loop():
    print("Poll loop started.")
    last_pull = 0
    last_heartbeat = 0
    PULL_INTERVAL = 20  # seconds - no need to pull every 2s, GitHub Actions only touches this hourly
    HEARTBEAT_INTERVAL = 60

    while True:
        _last_alive["ts"] = time.time()  # proof of life, checked by the watchdog below
        try:
            if time.time() - last_heartbeat >= HEARTBEAT_INTERVAL:
                print(f"Heartbeat - poll loop alive at {now_iso()}")
                last_heartbeat = time.time()

            if time.time() - last_pull >= PULL_INTERVAL:
                git_sync.pull_latest()
                last_pull = time.time()

            state = load_state()
            offset = state.get("last_update_id", 0)
            users = load_users()
            users = ensure_default_admin(users)

            from telegram_api import get_updates
            updates = get_updates(offset)
            if updates:
                print(f"Got {len(updates)} update(s), offset was {offset}")

            changed = False
            for update in updates:
                state["last_update_id"] = update["update_id"] + 1
                changed = True
                try:
                    if "callback_query" in update:
                        print(f"Handling callback from {update['callback_query']['from']['id']}")
                        handle_callback(update["callback_query"], users)
                    elif "message" in update:
                        print(f"Handling message from {update['message']['from']['id']}: {update['message'].get('text')}")
                        handle_message(update["message"], users)
                except Exception as e:
                    print(f"ERROR handling update: {e}")

            strikes_changed = check_broadcast_strikes(users)
            trials_changed = check_referral_trials(users)

            if changed or updates or strikes_changed or trials_changed:
                save_state(state)
                save_users(users)
                git_sync.push_changes(
                    "Bot state update [skip ci]",
                    ["state.json", "users.json", "broadcasts.json", "redeem_codes.json"],
                )
        except Exception as e:
            print(f"Poll loop error: {e}")

        time.sleep(POLL_INTERVAL)


def watchdog_loop():
    """If the poll loop ever stops updating its proof-of-life timestamp
    (hung on something we didn't anticipate), force-kill the whole process.
    Render detects a crashed process and restarts it automatically within
    seconds - this is separate from the Auto-Deploy setting we turned off,
    so it's safe and won't reintroduce the redeploy-on-every-commit problem."""
    WATCHDOG_CHECK_EVERY = 15
    STUCK_THRESHOLD = 90

    while True:
        time.sleep(WATCHDOG_CHECK_EVERY)
        stuck_for = time.time() - _last_alive["ts"]
        if stuck_for > STUCK_THRESHOLD:
            print(f"WATCHDOG: poll loop stuck for {stuck_for:.0f}s - forcing restart.")
            os._exit(1)


threading.Thread(target=poll_loop, daemon=True).start()
threading.Thread(target=watchdog_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
