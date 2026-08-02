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

os.environ["RENDER"] = "1"

import git_sync
git_sync.ensure_repo()
os.chdir(git_sync.REPO_DIR)

from flask import Flask
from config import BOT_TOKEN, ADMIN_CHAT_ID, API_BASE
from storage import load_state, save_state, load_users, save_users
from bot_commands import (
    handle_message, handle_callback, ensure_default_admin,
    check_broadcast_strikes,
)

import requests
requests.post(f"{API_BASE}/deleteWebhook", data={"drop_pending_updates": False}, timeout=15)

app = Flask(__name__)
POLL_INTERVAL = 2  # seconds between getUpdates calls - feels instant


@app.route("/")
def health():
    return "Galaxy Gamez bot is running.", 200


def poll_loop():
    print("Poll loop started.")
    while True:
        try:
            git_sync.pull_latest()

            state = load_state()
            offset = state.get("last_update_id", 0)
            users = load_users()
            users = ensure_default_admin(users)

            from telegram_api import get_updates
            updates = get_updates(offset)

            changed = False
            for update in updates:
                state["last_update_id"] = update["update_id"] + 1
                changed = True
                if "callback_query" in update:
                    handle_callback(update["callback_query"], users)
                elif "message" in update:
                    handle_message(update["message"], users)

            check_broadcast_strikes(users)

            if changed or updates:
                save_state(state)
                save_users(users)
                git_sync.push_changes(
                    "Bot state update [skip ci]",
                    ["state.json", "users.json", "broadcasts.json", "redeem_codes.json"],
                )
        except Exception as e:
            print(f"Poll loop error: {e}")

        time.sleep(POLL_INTERVAL)


threading.Thread(target=poll_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
