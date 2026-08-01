"""
Galaxy Gamez - Command Handler (bot_commands.py)
Runs every ~5 minutes via GitHub Actions (not an always-on bot).
"""

import requests
from datetime import datetime, timedelta

from config import (
    BOT_TOKEN, ADMIN_CHAT_ID, GITHUB_TOKEN, GITHUB_REPOSITORY,
    FORCE_JOIN_CHATS, SUPPORT_HANDLE, STRIKE_LIMIT, BROADCAST_GRACE_HOURS,
    API_BASE,
)
from storage import (
    load_state, save_state, load_stats, load_users, save_users,
    get_user, load_broadcasts, save_broadcasts, now_iso,
)
from telegram_api import (
    send_message, get_chat_member, get_chat, get_updates,
    answer_callback, message_still_exists,
)
from main import get_feed_entries, ensure_default_admin

CREDITS_LINE = (
    "\n\n┏━━━━━━━━━━━━━━━┓\n"
    "   𝐂𝐑𝐄𝐃𝐈𝐓𝐒: @GALAXYGAMEZSUPPORT\n"
    "┗━━━━━━━━━━━━━━━┛"
)
BOT_NAME = "𝐆𝐀𝐋𝐀𝐗𝐘 𝐆𝐀𝐌𝐄𝐙 𝐀𝐒𝐒𝐈𝐒𝐓𝐀𝐍𝐓"


# ---------------- KEYBOARDS ----------------

def public_keyboard():
    return {
        "keyboard": [
            ["▶️ Post Now", "🔄 Refresh"],
            ["⏭️ Skip", "🧪 Test"],
            ["📊 Stats", "📡 Channels"],
            ["➕ Add Channel", "📰 Add Blog"],
            ["⏸️ My Channel Pause", "▶️ My Channel Resume"],
            ["❓ Help"],
        ],
        "resize_keyboard": True,
    }


def admin_keyboard():
    return {
        "keyboard": [
            ["▶️ Post Now", "🔄 Refresh"],
            ["⏭️ Skip", "🧪 Test"],
            ["📊 Stats", "💚 Health"],
            ["📡 Channels", "⏸️ Pause"],
            ["▶️ Resume", "📢 Broadcast"],
            ["👥 Users", "⚙️ Advanced"],
            ["❓ Help"],
        ],
        "resize_keyboard": True,
    }


def advanced_keyboard():
    return {
        "keyboard": [
            ["🗑️ Reset History", "📜 Logs"],
            ["⬅️ Back"],
        ],
        "resize_keyboard": True,
    }


def force_join_keyboard():
    rows = [[{"text": c["label"], "url": c["url"]}] for c in FORCE_JOIN_CHATS]
    rows.append([{"text": "✅ I've Joined", "callback_data": "check_join"}])
    return {"inline_keyboard": rows}


def schedule_unit_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "⏰ Hours", "callback_data": "sched_unit_hours"}],
            [{"text": "📅 Days", "callback_data": "sched_unit_days"}],
        ]
    }


def schedule_hours_keyboard():
    from config import SCHEDULE_HOUR_OPTIONS
    row = [{"text": f"{h}hr", "callback_data": f"sched_hours_{h}"} for h in SCHEDULE_HOUR_OPTIONS]
    return {"inline_keyboard": [row[i:i + 3] for i in range(0, len(row), 3)]}


def schedule_days_keyboard():
    from config import SCHEDULE_DAY_OPTIONS
    row = [{"text": f"{d}d", "callback_data": f"sched_days_{d}"} for d in SCHEDULE_DAY_OPTIONS]
    return {"inline_keyboard": [row[i:i + 3] for i in range(0, len(row), 3)]}


# ---------------- FORCE-JOIN CHECK ----------------

def is_member(username, user_id):
    data = get_chat_member(f"@{username}", user_id)
    if not data.get("ok"):
        return False
    status = data["result"].get("status")
    return status in ("member", "administrator", "creator")


def missing_joins(user_id):
    missing = []
    for c in FORCE_JOIN_CHATS:
        if not is_member(c["username"], user_id):
            missing.append(c)
    return missing


def send_join_gate(chat_id):
    send_message(
        chat_id,
        "🔒 Join all of these first to use this bot:" + CREDITS_LINE,
        reply_markup=force_join_keyboard(),
    )


# ---------------- ADMIN CHECK ----------------

def is_admin(user_id):
    return str(user_id) == str(ADMIN_CHAT_ID)


# ---------------- COMMAND HANDLERS ----------------

def cmd_post(chat_id, user_id, users):
    from main import run_posting_cycle
    send_message(chat_id, "Starting a posting cycle now...")
    result = run_posting_cycle(manual=True)
    send_message(chat_id, f"Done.\n{result}")


def cmd_refresh(chat_id, user_id, users):
    u = get_user(users, user_id)
    if not u["channels"]:
        send_message(chat_id, "You haven't added a channel yet. Use ➕ Add Channel first.")
        return
    lines = ["Feed refreshed."]
    for ch in u["channels"]:
        entries = get_feed_entries(ch["blog_feed_url"])
        unposted = len([e for e in entries if e.link not in ch.get("posted", [])])
        lines.append(f"{ch['channel_id']}: {len(entries)} total, {unposted} unposted")
    send_message(chat_id, "\n".join(lines))


def cmd_skip(chat_id, user_id, users):
    u = get_user(users, user_id)
    if not u["channels"]:
        send_message(chat_id, "No channel added yet.")
        return
    ch = u["channels"][0]
    entries = get_feed_entries(ch["blog_feed_url"])
    posted = ch.setdefault("posted", [])
    for e in entries:
        if e.link not in posted:
            posted.append(e.link)
            send_message(chat_id, f"Skipped: {e.title}")
            return
    send_message(chat_id, "Nothing to skip - no unposted posts found.")


def cmd_reset(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    for u in users.values():
        for ch in u.get("channels", []):
            ch["posted"] = []
    send_message(chat_id, "Posted-history cleared for all channels. Next cycle starts fresh.")


def cmd_health(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    lines = ["HEALTH CHECK"]
    try:
        r = requests.get(f"{API_BASE}/getMe", timeout=15).json()
        lines.append(f"Telegram: OK ({r['result']['username']})" if r.get("ok") else "Telegram: FAILED")
    except Exception:
        lines.append("Telegram: FAILED")

    state = load_state()
    lines.append(f"Global posting paused: {state.get('paused', False)}")
    lines.append(f"Total users: {len(users)}")
    total_channels = sum(len(u.get("channels", [])) for u in users.values())
    lines.append(f"Total channels connected: {total_channels}")

    if GITHUB_TOKEN and GITHUB_REPOSITORY:
        try:
            r = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/runs?per_page=1",
                headers={"Authorization": f"Bearer {GITHUB_TOKEN}"},
                timeout=15,
            ).json()
            run = r["workflow_runs"][0]
            lines.append(f"Last automation run: {run['name']} - {run['conclusion'] or run['status']}")
        except Exception:
            lines.append("GitHub Actions status: unavailable")

    send_message(chat_id, "\n".join(lines))


def cmd_stats(chat_id, user_id, users):
    stats = load_stats()
    u = get_user(users, user_id)
    send_message(
        chat_id,
        f"STATS FOR {stats.get('date')}\n"
        f"Posts sent today (all users): {stats.get('posts_sent', 0)}\n"
        f"Successful: {stats.get('success', 0)}\n"
        f"Failed: {stats.get('failed', 0)}\n"
        f"Your channels: {len(u['channels'])}",
    )


def cmd_logs(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    try:
        with open("last_run_log.txt", "r") as f:
            content = f.read()
        send_message(chat_id, content[-3500:] if content else "Log file is empty.")
    except FileNotFoundError:
        send_message(chat_id, "No logs yet.")


def cmd_test(chat_id, user_id, users):
    send_message(chat_id, "Test message - the bot and command system are working." + CREDITS_LINE)


def cmd_channels(chat_id, user_id, users):
    u = get_user(users, user_id)
    if not u["channels"]:
        send_message(chat_id, "No channel added yet. Use ➕ Add Channel.")
        return
    lines = ["CHANNEL CHECK"]
    for ch in u["channels"]:
        r = get_chat(ch["channel_id"])
        if r.get("ok"):
            lines.append(f"✓ {r['result'].get('title', ch['channel_id'])} - reachable")
        else:
            lines.append(f"✗ {ch['channel_id']} - {r.get('description', 'error')}")
    send_message(chat_id, "\n".join(lines))


def cmd_pause(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only. Use ⏸️ My Channel Pause to pause just your own channel.")
        return
    state = load_state()
    state["paused"] = True
    save_state(state)
    send_message(chat_id, "Global automatic posting paused for ALL users.")


def cmd_resume(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    state = load_state()
    state["paused"] = False
    save_state(state)
    send_message(chat_id, "Global automatic posting resumed.")


def cmd_my_pause(chat_id, user_id, users):
    u = get_user(users, user_id)
    if not u["channels"]:
        send_message(chat_id, "No channel added yet.")
        return
    for ch in u["channels"]:
        ch["paused"] = True
    send_message(chat_id, "Your channel(s) posting paused.")


def cmd_my_resume(chat_id, user_id, users):
    u = get_user(users, user_id)
    if not u["channels"]:
        send_message(chat_id, "No channel added yet.")
        return
    for ch in u["channels"]:
        ch["paused"] = False
    send_message(chat_id, "Your channel(s) posting resumed.")


def cmd_users(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    lines = [f"CONNECTED USERS ({len(users)})"]
    for uid, u in users.items():
        if uid == "__admin__":
            continue
        lines.append(f"{uid}: {len(u.get('channels', []))} channel(s), strikes {u.get('strikes', 0)}/{STRIKE_LIMIT}, banned: {u.get('banned', False)}")
    send_message(chat_id, "\n".join(lines) if len(lines) > 1 else "No external users yet.")


def cmd_help(chat_id, user_id, users):
    if is_admin(user_id):
        text = (
            f"❏ 𝐀𝐃𝐌𝐈𝐍 𝐂𝐎𝐌𝐌𝐀𝐍𝐃𝐒\n\n"
            f"╭➤ 𝐏𝐎𝐒𝐓𝐈𝐍𝐆\n"
            f"│ ▶️ Post Now — post right now\n"
            f"│ 🔄 Refresh — check feeds for new posts\n"
            f"│ ⏭️ Skip — skip next unposted post\n"
            f"│\n"
            f"├➤ 𝐒𝐘𝐒𝐓𝐄𝐌\n"
            f"│ 💚 Health — system status\n"
            f"│ 📊 Stats — today's stats\n"
            f"│ 📡 Channels — check channel access\n"
            f"│ ⏸️ Pause / ▶️ Resume — pause/resume ALL users\n"
            f"│\n"
            f"├➤ 𝐆𝐑𝐎𝐖𝐓𝐇\n"
            f"│ 📢 Broadcast — send ad/promo to every channel\n"
            f"│ 👥 Users — list connected users\n"
            f"│\n"
            f"╰➤ 𝐀𝐃𝐕𝐀𝐍𝐂𝐄𝐃 (⚙️ menu)\n"
            f"   🗑️ Reset History · 📜 Logs\n\n"
            f"⏱️ Commands are checked every ~5 min, not instantly."
            + CREDITS_LINE
        )
    else:
        text = (
            f"❏ 𝐂𝐎𝐌𝐌𝐀𝐍𝐃𝐒\n\n"
            f"╭➤ 𝐏𝐎𝐒𝐓𝐈𝐍𝐆\n"
            f"│ ▶️ Post Now — post now (your channel)\n"
            f"│ 🔄 Refresh — check your feed\n"
            f"│ ⏭️ Skip — skip your next unposted post\n"
            f"│ 🧪 Test — send a test message\n"
            f"│\n"
            f"├➤ 𝐂𝐇𝐀𝐍𝐍𝐄𝐋\n"
            f"│ 📊 Stats — today's stats\n"
            f"│ 📡 Channels — check your channel access\n"
            f"│ ➕ Add Channel — connect your channel\n"
            f"│ 📰 Add Blog — set your Blogger feed\n"
            f"│\n"
            f"╰➤ ⏸️/▶️ My Channel Pause/Resume\n\n"
            f"⚠️ This bot is FREE. In exchange, sponsored posts may appear "
            f"on your channel occasionally. Deleting one within 4hrs = "
            f"channel removed. 3 strikes = permanent ban.\n\n"
            f"⏱️ Commands are checked every ~5 min, not instantly."
            + CREDITS_LINE
        )
    send_message(chat_id, text)


# ---------------- ONBOARDING: ADD CHANNEL / ADD BLOG ----------------

def cmd_add_channel(chat_id, user_id, users):
    u = get_user(users, user_id)
    u["onboarding"]["step"] = "awaiting_channel"
    send_message(
        chat_id,
        "Make this bot an ADMIN in your Telegram channel (needs 'Post Messages' "
        "permission), then forward any message from that channel here, or send "
        "its @username.\n\n"
        "⚠️ By connecting your channel you agree this bot may occasionally post "
        "sponsored content. Deleting a sponsored post within 4hrs = channel "
        "removed. 3 strikes = permanent ban."
        + CREDITS_LINE,
    )


def cmd_add_blog(chat_id, user_id, users):
    u = get_user(users, user_id)
    if not u["channels"]:
        send_message(chat_id, "Add your channel first with ➕ Add Channel.")
        return
    u["onboarding"]["step"] = "awaiting_blog"
    send_message(chat_id, "Send your Blogger feed URL, e.g.\nhttps://yourblog.blogspot.com/feeds/posts/default?max-results=500")


def handle_onboarding_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    step = u["onboarding"].get("step")

    if step == "awaiting_channel":
        channel_id = None
        if message.get("forward_from_chat"):
            channel_id = message["forward_from_chat"]["id"]
        else:
            text = message.get("text", "").strip().lstrip("@")
            if text:
                r = get_chat(f"@{text}")
                if r.get("ok"):
                    channel_id = r["result"]["id"]

        if not channel_id:
            send_message(chat_id, "Couldn't detect a channel. Forward a message from it, or send its @username.")
            return True

        member = get_chat_member(channel_id, chat_id_of_bot(u) or "")
        u["channels"].append({
            "channel_id": channel_id,
            "title": "Connected channel",
            "blog_feed_url": "",
            "paused": True,  # stays paused until a blog feed + schedule are set
            "posted": [],
            "interval_hours": None,
            "last_posted_at": None,
        })
        u["onboarding"]["step"] = None
        send_message(chat_id, "Channel connected ✅. Now send 📰 Add Blog to set your Blogger feed.")
        return True

    if step == "awaiting_blog":
        text = message.get("text", "").strip()
        if not text.startswith("http"):
            send_message(chat_id, "That doesn't look like a valid feed URL. Try again.")
            return True
        u["channels"][-1]["blog_feed_url"] = text
        u["onboarding"]["step"] = None
        send_message(
            chat_id,
            "Blog feed set ✅. Last step - how often should this channel post?",
            reply_markup=schedule_unit_keyboard(),
        )
        return True

    return False


def chat_id_of_bot(u):
    return None  # placeholder, not required for getChatMember calls above


# ---------------- BROADCAST + STRIKE SYSTEM ----------------

def cmd_broadcast_start(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    u = get_user(users, user_id)
    u["onboarding"]["step"] = "awaiting_broadcast"
    send_message(chat_id, "Send the promo/ad text now. It will go to every connected channel.")


def handle_broadcast_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_broadcast":
        return False

    text = message.get("text", "")
    u["onboarding"]["step"] = None
    broadcasts = load_broadcasts()
    sent, failed = 0, 0

    for uid, target in users.items():
        for ch in target.get("channels", []):
            r = send_message(ch["channel_id"], text)
            if r.get("ok"):
                sent += 1
                broadcasts.append({
                    "channel_id": ch["channel_id"],
                    "user_id": uid,
                    "message_id": r["result"]["message_id"],
                    "sent_at": now_iso(),
                    "checked": False,
                })
            else:
                failed += 1

    save_broadcasts(broadcasts)
    send_message(chat_id, f"Broadcast sent. Delivered: {sent}, Failed: {failed}")
    return True


def check_broadcast_strikes(users):
    """Run every cycle. Checks broadcasts older than the grace period to see
    if they were deleted, and applies strikes/bans."""
    broadcasts = load_broadcasts()
    changed = False

    for b in broadcasts:
        if b.get("checked"):
            continue
        sent_at = datetime.fromisoformat(b["sent_at"])
        if datetime.utcnow() - sent_at < timedelta(hours=BROADCAST_GRACE_HOURS):
            continue

        b["checked"] = True
        changed = True
        if not message_still_exists(b["channel_id"], b["message_id"]):
            uid = b["user_id"]
            u = get_user(users, uid)
            u["strikes"] = u.get("strikes", 0) + 1
            u["channels"] = [c for c in u["channels"] if c["channel_id"] != b["channel_id"]]

            if u["strikes"] >= STRIKE_LIMIT:
                u["banned"] = True
                send_message(uid, f"🚫 3rd strike - you're permanently banned from this bot.{CREDITS_LINE}")
            else:
                send_message(
                    uid,
                    f"⚠️ Strike {u['strikes']}/{STRIKE_LIMIT} - your channel was removed for "
                    f"deleting a sponsored post before {BROADCAST_GRACE_HOURS}hrs. "
                    f"{STRIKE_LIMIT} strikes = permanent ban.{CREDITS_LINE}",
                )

    if changed:
        save_broadcasts(broadcasts)


# ---------------- COMMAND ROUTING ----------------

TEXT_COMMANDS = {
    "/post": cmd_post, "▶️ Post Now": cmd_post,
    "/refresh": cmd_refresh, "🔄 Refresh": cmd_refresh,
    "/skip": cmd_skip, "⏭️ Skip": cmd_skip,
    "/reset": cmd_reset, "🗑️ Reset History": cmd_reset,
    "/health": cmd_health, "💚 Health": cmd_health,
    "/stats": cmd_stats, "📊 Stats": cmd_stats,
    "/logs": cmd_logs, "📜 Logs": cmd_logs,
    "/test": cmd_test, "🧪 Test": cmd_test,
    "/channels": cmd_channels, "📡 Channels": cmd_channels,
    "/pause": cmd_pause, "⏸️ Pause": cmd_pause,
    "/resume": cmd_resume, "▶️ Resume": cmd_resume,
    "⏸️ My Channel Pause": cmd_my_pause,
    "▶️ My Channel Resume": cmd_my_resume,
    "/users": cmd_users, "👥 Users": cmd_users,
    "/help": cmd_help, "❓ Help": cmd_help,
    "➕ Add Channel": cmd_add_channel,
    "📰 Add Blog": cmd_add_blog,
    "📢 Broadcast": cmd_broadcast_start,
}


def keyboard_for(user_id):
    return admin_keyboard() if is_admin(user_id) else public_keyboard()


def handle_message(message, users):
    chat = message["chat"]
    chat_id = str(chat["id"])
    user_id = str(message["from"]["id"])

    # Only respond in private chats (DMs to the bot)
    if chat.get("type") != "private":
        return

    if user_id != str(ADMIN_CHAT_ID):
        missing = missing_joins(user_id)
        if missing:
            send_join_gate(chat_id)
            return

    text = message.get("text", "").strip()

    if text == "⚙️ Advanced" and is_admin(user_id):
        send_message(chat_id, "Advanced menu:", reply_markup=advanced_keyboard())
        return
    if text == "⬅️ Back":
        send_message(chat_id, "Main menu:", reply_markup=keyboard_for(user_id))
        return
    if text in ("/start", "/help") and text == "/start":
        welcome = (
            f"❏ {BOT_NAME}\n\n"
            f"I auto-post fresh PPSSPP games to your Telegram channel every "
            f"few hours — connect your channel + Blogger feed and I take it "
            f"from there.\n\n"
            f"Tap ❓ Help below to see everything I can do."
            + CREDITS_LINE
        )
        send_message(chat_id, welcome, reply_markup=keyboard_for(user_id))
        cmd_help(chat_id, user_id, users)
        return

    if handle_onboarding_message(chat_id, user_id, users, message):
        return
    if handle_broadcast_message(chat_id, user_id, users, message):
        return

    handler = TEXT_COMMANDS.get(text)
    if handler:
        handler(chat_id, user_id, users)
    elif text.startswith("/"):
        send_message(chat_id, "Unknown command. Send /help to see the list.")


def handle_callback(callback, users):
    user_id = str(callback["from"]["id"])
    chat_id = str(callback["message"]["chat"]["id"])
    data = callback.get("data")

    if data == "check_join":
        missing = missing_joins(user_id)
        if missing:
            answer_callback(callback["id"], "You still haven't joined everything.")
        else:
            answer_callback(callback["id"], "You're in! ✅")
            send_message(chat_id, "Access unlocked ✅ Welcome!", reply_markup=keyboard_for(user_id))
        return

    if data == "sched_unit_hours":
        answer_callback(callback["id"])
        send_message(chat_id, "Pick your posting interval:", reply_markup=schedule_hours_keyboard())
        return

    if data == "sched_unit_days":
        answer_callback(callback["id"])
        send_message(chat_id, "Pick your posting interval:", reply_markup=schedule_days_keyboard())
        return

    if data.startswith("sched_hours_") or data.startswith("sched_days_"):
        u = get_user(users, user_id)
        if not u["channels"]:
            answer_callback(callback["id"], "No channel found - start over with Add Channel.")
            return
        value = int(data.rsplit("_", 1)[1])
        interval_hours = value if data.startswith("sched_hours_") else value * 24
        ch = u["channels"][-1]
        ch["interval_hours"] = interval_hours
        ch["paused"] = False
        label = f"{value}hr" if data.startswith("sched_hours_") else f"{value} day{'s' if value != 1 else ''}"
        answer_callback(callback["id"], f"Set to every {label} ✅")
        send_message(
            chat_id,
            f"All set ✅ Your channel will now auto-post every {label}." + CREDITS_LINE,
            reply_markup=keyboard_for(user_id),
        )
        return


# ---------------- ENTRY POINT ----------------

def main():
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        print("Missing TELEGRAM_BOT_TOKEN or ADMIN_CHAT_ID.")
        return

    state = load_state()
    offset = state.get("last_update_id", 0)
    users = load_users()
    users = ensure_default_admin(users)

    # Make sure broadcasts.json always exists so the workflow's git add never fails
    save_broadcasts(load_broadcasts())

    updates = get_updates(offset)
    if updates:
        for update in updates:
            state["last_update_id"] = update["update_id"] + 1
            if "callback_query" in update:
                handle_callback(update["callback_query"], users)
            elif "message" in update:
                handle_message(update["message"], users)
        save_state(state)
    else:
        print("No new commands.")

    check_broadcast_strikes(users)
    save_users(users)


if __name__ == "__main__":
    main()
