"""
Galaxy Gamez - Command Handler (bot_commands.py)
Runs every ~5 minutes via GitHub Actions (not an always-on bot).
"""

import requests
from datetime import datetime, timedelta

from config import (
    BOT_TOKEN, ADMIN_CHAT_ID, GITHUB_TOKEN, GITHUB_REPOSITORY,
    FORCE_JOIN_CHATS, SUPPORT_HANDLE, STRIKE_LIMIT, BROADCAST_GRACE_HOURS,
    API_BASE, MAX_CHANNELS_FREE, MAX_CHANNELS_PAID, PAYMENT_INFO,
    MIN_MONTHLY_PRICE_NAIRA, MIN_YEARLY_PRICE_NAIRA, GEMZ_PACKAGES,
)
from storage import (
    load_state, save_state, load_stats, load_users, save_users,
    get_user, load_broadcasts, save_broadcasts, now_iso,
    load_redeem_codes, save_redeem_codes,
)
from telegram_api import (
    send_message, get_chat_member, get_chat, get_updates,
    answer_callback, message_still_exists, forward_message,
)
from main import get_feed_entries, ensure_default_admin
from terms import TERMS_TEXT
from estimator import estimate_days, format_duration
from textstyle import box
import random
import string

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
            ["💎 My Gemz", "💰 Buy Gemz"],
            ["🎁 Redeem Code", "📈 Estimate Usage"],
            ["🐛 Report Bug", "❓ Help"],
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
            ["🎟️ Generate Code", "💳 Credit User"],
            ["📈 Estimate Usage", "🐛 Report Bug"],
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


def posts_per_cycle_keyboard():
    from config import POSTS_PER_CYCLE_OPTIONS
    row = [{"text": f"{n} post{'s' if n != 1 else ''}", "callback_data": f"ppc_{n}"} for n in POSTS_PER_CYCLE_OPTIONS]
    return {"inline_keyboard": [row[i:i + 2] for i in range(0, len(row), 2)]}


def terms_keyboard():
    return {"inline_keyboard": [[{"text": "✅ I Agree", "callback_data": "accept_terms"}]]}


def estimate_channels_keyboard():
    return {"inline_keyboard": [[{"text": str(n), "callback_data": f"est_ch_{n}"} for n in range(1, 5)]]}


def estimate_unit_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "⏰ Hours", "callback_data": "est_unit_hours"}],
            [{"text": "📅 Days", "callback_data": "est_unit_days"}],
        ]
    }


def estimate_hours_keyboard():
    from config import SCHEDULE_HOUR_OPTIONS
    row = [{"text": f"{h}hr", "callback_data": f"est_hours_{h}"} for h in SCHEDULE_HOUR_OPTIONS]
    return {"inline_keyboard": [row[i:i + 3] for i in range(0, len(row), 3)]}


def estimate_days_keyboard():
    from config import SCHEDULE_DAY_OPTIONS
    row = [{"text": f"{d}d", "callback_data": f"est_days_{d}"} for d in SCHEDULE_DAY_OPTIONS]
    return {"inline_keyboard": [row[i:i + 3] for i in range(0, len(row), 3)]}


def estimate_ppc_keyboard():
    from config import POSTS_PER_CYCLE_OPTIONS
    row = [{"text": f"{n} post{'s' if n != 1 else ''}", "callback_data": f"est_ppc_{n}"} for n in POSTS_PER_CYCLE_OPTIONS]
    return {"inline_keyboard": [row[i:i + 2] for i in range(0, len(row), 2)]}


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
            f"├➤ 𝐆𝐄𝐌𝐙\n"
            f"│ 🎟️ Generate Code — create a user-locked redeem code\n"
            f"│ 💳 Credit User — manually credit Gemz after payment\n"
            f"│ /unlockchannels <user_id> — raise a user's channel limit to {MAX_CHANNELS_PAID}\n"
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
            f"├➤ 𝐂𝐇𝐀𝐍𝐍𝐄𝐋 (max {MAX_CHANNELS_FREE} free, {MAX_CHANNELS_PAID} paid)\n"
            f"│ 📊 Stats — today's stats\n"
            f"│ 📡 Channels — check your channel access\n"
            f"│ ➕ Add Channel — connect your channel\n"
            f"│ 📰 Add Blog — set your Blogger feed\n"
            f"│\n"
            f"├➤ 𝐆𝐄𝐌𝐙\n"
            f"│ 💎 My Gemz — check your balance\n"
            f"│ 💰 Buy Gemz — payment info + purchase\n"
            f"│ 🎁 Redeem Code — use a code from the team\n"
            f"│ 📈 Estimate Usage — see how long Gemz will last\n"
            f"│\n"
            f"╰➤ ⏸️/▶️ My Channel Pause/Resume\n\n"
            f"🐛 Report Bug — send an issue straight to the team\n\n"
            f"⚠️ This bot is FREE at the free tier. In exchange, sponsored "
            f"posts may appear on your channel occasionally. Deleting one "
            f"within 4hrs = channel removed. 3 strikes = permanent ban.\n\n"
            f"⏱️ Commands are checked every ~5 min, not instantly."
            + CREDITS_LINE
        )
    send_message(chat_id, text)


# ---------------- ONBOARDING: ADD CHANNEL / ADD BLOG ----------------

def cmd_add_channel(chat_id, user_id, users):
    u = get_user(users, user_id)

    if not is_admin(user_id):
        limit = MAX_CHANNELS_PAID if u.get("extra_channel_slots") else MAX_CHANNELS_FREE
        if len(u["channels"]) >= limit:
            if limit == MAX_CHANNELS_FREE:
                send_message(
                    chat_id,
                    f"You're at the free limit of {MAX_CHANNELS_FREE} channel(s). "
                    f"To unlock up to {MAX_CHANNELS_PAID}, contact {SUPPORT_HANDLE}."
                    + CREDITS_LINE,
                )
            else:
                send_message(
                    chat_id,
                    f"You've reached the maximum of {MAX_CHANNELS_PAID} channels per account."
                    + CREDITS_LINE,
                )
            return

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
            "posts_per_cycle": None,
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


# ---------------- BUG REPORTS ----------------

def cmd_report_bug(chat_id, user_id, users):
    u = get_user(users, user_id)
    u["onboarding"]["step"] = "awaiting_bug_report"
    send_message(
        chat_id,
        "🐛 Describe the bug or issue you're facing - be as specific as possible "
        "(what you tapped, what you expected, what happened instead). "
        "It goes straight to the Galaxy Gamez team." + CREDITS_LINE,
    )


def handle_bug_report_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_bug_report":
        return False

    text = message.get("text", "")
    u["onboarding"]["step"] = None

    admin_note = (
        f"{box('BUG REPORT')}\n"
        f"From user: {user_id}\n\n"
        f"{text}"
    )
    send_message(ADMIN_CHAT_ID, admin_note)
    send_message(chat_id, "✅ Bug report sent - thanks for the heads up." + CREDITS_LINE)
    return True


# ---------------- GEMZ: BALANCE, PURCHASE, PAYMENT PROOF ----------------

def cmd_my_gemz(chat_id, user_id, users):
    u = get_user(users, user_id)
    send_message(chat_id, f"💎 Your balance: {u.get('gemz_balance', 0)} Gemz" + CREDITS_LINE)


def cmd_buy_gemz(chat_id, user_id, users):
    lines = [
        box("BUY GEMZ"),
        "",
        f"Pay to:",
        f"🏦 {PAYMENT_INFO['bank_name']}",
        f"Acct: {PAYMENT_INFO['account_number']}",
        f"Name: {PAYMENT_INFO['account_name']}",
        "",
        f"Minimum monthly package: ₦{MIN_MONTHLY_PRICE_NAIRA:,}",
        f"Minimum yearly package: ₦{MIN_YEARLY_PRICE_NAIRA:,}",
        "",
        "⚠️ The Naira amount you pay is NOT the same number as the Gemz you "
        "receive - Gemz packages are shown below, check the exact amount "
        "before paying.",
        "",
        "⚠️ Gemz are spent based on YOUR actual usage (posts sent + channels "
        "connected) - not a fixed calendar month. Use 📈 Estimate Usage to see "
        "how long a purchase will realistically last for your setup before "
        "you pay.",
        "",
        "After paying, send the payment screenshot here as a photo - it goes "
        "straight to the team, no need to message anyone separately. You'll "
        "be credited once confirmed.",
    ]
    if GEMZ_PACKAGES:
        lines.insert(2, "")
        for p in GEMZ_PACKAGES:
            lines.insert(3, f"• {p['label']}: {p['gemz']} Gemz — ₦{p['price_naira']:,} ({p['period']})")

    u = get_user(users, user_id)
    u["onboarding"]["step"] = "awaiting_payment_proof"
    send_message(chat_id, "\n".join(lines) + CREDITS_LINE)


def handle_payment_proof_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_payment_proof":
        return False
    if not message.get("photo"):
        return False  # wait for an actual photo, ignore other text in the meantime

    u["onboarding"]["step"] = None
    forward_message(ADMIN_CHAT_ID, chat_id, message["message_id"])
    send_message(ADMIN_CHAT_ID, f"👆 Payment screenshot from user {user_id}. Use 💳 Credit User once confirmed.")
    send_message(chat_id, "✅ Screenshot received - awaiting confirmation. You'll be notified once credited." + CREDITS_LINE)
    return True


# ---------------- ADMIN: CREDIT USER / UNLOCK CHANNEL SLOTS ----------------

def cmd_credit_start(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    u = get_user(users, user_id)
    u["onboarding"]["step"] = "awaiting_credit"
    send_message(chat_id, "Send: <user_id> <gemz_amount>  e.g. 123456789 5000")


def handle_credit_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_credit":
        return False
    u["onboarding"]["step"] = None

    parts = message.get("text", "").split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        send_message(chat_id, "Format: <user_id> <amount>")
        return True

    target_id, amount = parts[0], int(parts[1])
    target = get_user(users, target_id)
    target["gemz_balance"] = target.get("gemz_balance", 0) + amount
    send_message(chat_id, f"✅ Credited {amount} Gemz to {target_id}. New balance: {target['gemz_balance']}")
    send_message(target_id, f"💎 {amount} Gemz added to your balance by the team." + CREDITS_LINE)
    return True


def cmd_unlock_slots(chat_id, user_id, users, args_text):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    target_id = args_text.strip()
    if not target_id.isdigit():
        send_message(chat_id, "Usage: /unlockchannels <user_id>")
        return
    target = get_user(users, target_id)
    target["extra_channel_slots"] = True
    send_message(chat_id, f"✅ {target_id} can now connect up to {MAX_CHANNELS_PAID} channels.")
    send_message(target_id, f"🔓 Your account can now connect up to {MAX_CHANNELS_PAID} channels." + CREDITS_LINE)


# ---------------- REDEEM CODES ----------------

def _generate_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def cmd_gencode_start(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    u = get_user(users, user_id)
    u["onboarding"]["step"] = "awaiting_gencode"
    send_message(chat_id, "Send: <user_id> <gemz_amount>  e.g. 123456789 500")


def handle_gencode_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_gencode":
        return False
    u["onboarding"]["step"] = None

    parts = message.get("text", "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        send_message(chat_id, "Format: <user_id> <amount>")
        return True

    target_id, amount = parts[0], int(parts[1])
    codes = load_redeem_codes()

    # Prevent generating a new code while the user already has an unused one
    active = [c for c in codes if c["user_id"] == target_id and not c["used"]]
    if active:
        send_message(
            chat_id,
            f"❌ {target_id} already has an unused code ({active[0]['code']}). "
            f"They must redeem or you must void it before generating another.",
        )
        return True

    code = _generate_code()
    codes.append({
        "code": code, "user_id": target_id, "amount": amount,
        "used": False, "created_at": now_iso(),
    })
    save_redeem_codes(codes)
    send_message(chat_id, f"✅ Code generated for {target_id}: {code} (worth {amount} Gemz). Send it to them directly.")
    return True


def cmd_redeem_start(chat_id, user_id, users):
    u = get_user(users, user_id)
    u["onboarding"]["step"] = "awaiting_redeem"
    send_message(chat_id, "🎁 Enter your redeem code:")


def handle_redeem_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_redeem":
        return False
    u["onboarding"]["step"] = None

    entered = message.get("text", "").strip().upper()
    codes = load_redeem_codes()
    match = next((c for c in codes if c["code"] == entered and c["user_id"] == str(user_id)), None)

    if not match:
        send_message(chat_id, "❌ Invalid code, or this code isn't assigned to you." + CREDITS_LINE)
        return True
    if match["used"]:
        send_message(chat_id, "❌ This code has already been used and can't be redeemed again." + CREDITS_LINE)
        return True

    match["used"] = True
    save_redeem_codes(codes)
    u["gemz_balance"] = u.get("gemz_balance", 0) + match["amount"]
    send_message(chat_id, f"✅ Redeemed! +{match['amount']} Gemz. New balance: {u['gemz_balance']}" + CREDITS_LINE)
    return True


# ---------------- USAGE ESTIMATOR ----------------

def cmd_estimate_start(chat_id, user_id, users):
    u = get_user(users, user_id)
    u["onboarding"]["estimate"] = {}
    send_message(chat_id, "📈 How many channels are you running?", reply_markup=estimate_channels_keyboard())


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
    "/reportbug": cmd_report_bug, "🐛 Report Bug": cmd_report_bug,
    "💎 My Gemz": cmd_my_gemz, "/mygemz": cmd_my_gemz,
    "💰 Buy Gemz": cmd_buy_gemz, "/buygemz": cmd_buy_gemz,
    "🎁 Redeem Code": cmd_redeem_start, "/redeem": cmd_redeem_start,
    "📈 Estimate Usage": cmd_estimate_start, "/estimate": cmd_estimate_start,
    "🎟️ Generate Code": cmd_gencode_start,
    "💳 Credit User": cmd_credit_start,
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

    u = get_user(users, user_id)
    if not is_admin(user_id) and not u.get("terms_accepted"):
        send_message(chat_id, TERMS_TEXT, reply_markup=terms_keyboard())
        return

    text = message.get("text", "").strip()

    if text.startswith("/unlockchannels"):
        cmd_unlock_slots(chat_id, user_id, users, text[len("/unlockchannels"):])
        return

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

    if handle_payment_proof_message(chat_id, user_id, users, message):
        return
    if handle_onboarding_message(chat_id, user_id, users, message):
        return
    if handle_broadcast_message(chat_id, user_id, users, message):
        return
    if handle_bug_report_message(chat_id, user_id, users, message):
        return
    if handle_gencode_message(chat_id, user_id, users, message):
        return
    if handle_credit_message(chat_id, user_id, users, message):
        return
    if handle_redeem_message(chat_id, user_id, users, message):
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
        label = f"{value}hr" if data.startswith("sched_hours_") else f"{value} day{'s' if value != 1 else ''}"
        answer_callback(callback["id"], f"Set to every {label} ✅")
        send_message(
            chat_id,
            f"Interval set to every {label} ✅. Last step - how many posts per cycle?",
            reply_markup=posts_per_cycle_keyboard(),
        )
        return

    if data.startswith("ppc_"):
        u = get_user(users, user_id)
        if not u["channels"]:
            answer_callback(callback["id"], "No channel found - start over with Add Channel.")
            return
        n = int(data.split("_", 1)[1])
        ch = u["channels"][-1]
        ch["posts_per_cycle"] = n
        ch["paused"] = False
        answer_callback(callback["id"], f"Set to {n} post(s) per cycle ✅")
        interval_hours = ch.get("interval_hours", 3)
        interval_label = f"{interval_hours}hr" if interval_hours < 24 else f"{interval_hours // 24} day(s)"
        send_message(
            chat_id,
            f"All set ✅ Your channel will post {n} game(s) every {interval_label}." + CREDITS_LINE,
            reply_markup=keyboard_for(user_id),
        )
        return

    if data == "accept_terms":
        u = get_user(users, user_id)
        u["terms_accepted"] = True
        answer_callback(callback["id"], "Thanks!")
        send_message(chat_id, "✅ Terms accepted. Welcome to Galaxy Gamez!", reply_markup=keyboard_for(user_id))
        return

    if data.startswith("est_ch_"):
        n = int(data.rsplit("_", 1)[1])
        u = get_user(users, user_id)
        u["onboarding"]["estimate"] = {"channels": n}
        answer_callback(callback["id"])
        send_message(chat_id, "Now pick your posting schedule:", reply_markup=estimate_unit_keyboard())
        return

    if data == "est_unit_hours":
        answer_callback(callback["id"])
        send_message(chat_id, "Pick your posting interval:", reply_markup=estimate_hours_keyboard())
        return

    if data == "est_unit_days":
        answer_callback(callback["id"])
        send_message(chat_id, "Pick your posting interval:", reply_markup=estimate_days_keyboard())
        return

    if data.startswith("est_hours_") or data.startswith("est_days_"):
        value = int(data.rsplit("_", 1)[1])
        interval_hours = value if data.startswith("est_hours_") else value * 24
        u = get_user(users, user_id)
        u["onboarding"].setdefault("estimate", {})["interval_hours"] = interval_hours
        answer_callback(callback["id"])
        send_message(chat_id, "Last one - posts per cycle?", reply_markup=estimate_ppc_keyboard())
        return

    if data.startswith("est_ppc_"):
        n = int(data.rsplit("_", 1)[1])
        u = get_user(users, user_id)
        est = u["onboarding"].get("estimate", {})
        channels = est.get("channels")
        interval_hours = est.get("interval_hours")
        u["onboarding"]["estimate"] = {}
        answer_callback(callback["id"])

        if not channels or not interval_hours:
            send_message(chat_id, "Something went wrong - start over with 📈 Estimate Usage.")
            return

        d5000 = estimate_days(5000, channels, interval_hours, n)
        d10000 = estimate_days(10000, channels, interval_hours, n)
        interval_label = f"{interval_hours}hr" if interval_hours < 24 else f"{interval_hours // 24} day(s)"
        send_message(
            chat_id,
            f"{box('USAGE ESTIMATE')}\n\n"
            f"Setup: {channels} channel(s), {n} post(s) every {interval_label}\n\n"
            f"5,000 Gemz lasts: {format_duration(d5000)}\n"
            f"10,000 Gemz lasts: {format_duration(d10000)}\n\n"
            f"Tap 💰 Buy Gemz when ready." + CREDITS_LINE,
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

    # Make sure broadcasts.json/redeem_codes.json always exist so the workflow's git add never fails
    save_broadcasts(load_broadcasts())
    save_redeem_codes(load_redeem_codes())

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
