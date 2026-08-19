"""
Galaxy Gamez - Command Handler (bot_commands.py)
Runs every ~5 minutes via GitHub Actions (not an always-on bot).
"""

import requests
from datetime import datetime, timedelta, date

from config import (
    BOT_TOKEN, ADMIN_CHAT_ID, GITHUB_TOKEN, GITHUB_REPOSITORY,
    FORCE_JOIN_CHATS, SUPPORT_HANDLE, STRIKE_LIMIT, BROADCAST_GRACE_HOURS,
    API_BASE, MAX_CHANNELS_FREE, MAX_CHANNELS_PAID, PAYMENT_INFO,
    MIN_MONTHLY_PRICE_NAIRA, MIN_YEARLY_PRICE_NAIRA, GEMZ_PACKAGES, NAIRA_PER_GEMZ,
    REFERRAL_REWARD_GEMZ, BOT_USERNAME, GEMZ_COST_PER_CHANNEL_PER_DAY,
    POST_NOW_COOLDOWN_SECONDS,
)
from storage import (
    load_state, save_state, load_stats, load_users, save_users,
    get_user, load_broadcasts, save_broadcasts, now_iso,
    load_redeem_codes, save_redeem_codes, load_orders, save_orders,
    load_scheduled_broadcasts, save_scheduled_broadcasts,
)
from telegram_api import (
    send_message, get_chat_member, get_chat, get_updates,
    answer_callback, message_still_exists, forward_message, copy_message,
    send_photo,
)
from msg_format import extract_message_content, build_ad_html
from main import get_feed_entries, ensure_default_admin
from terms import TERMS_TEXT
from estimator import estimate_days, format_duration
from feed_discovery import discover_feed
from textstyle import box
import random
import string

CREDITS_LINE = (
    "\n\n┏━━━━━━━━━━━━━━━┓\n"
    "   𝐂𝐑𝐄𝐃𝐈𝐓𝐒: @GALAXYGAMEZSUPPORT\n"
    "┗━━━━━━━━━━━━━━━┛"
)
BOT_NAME = "𝐆𝐀𝐋𝐀𝐗𝐘 𝐀𝐔𝐓𝐎 𝐏𝐎𝐒𝐓𝐄𝐑"


# ---------------- KEYBOARDS ----------------

def public_keyboard():
    return {
        "keyboard": [
            ["▶️ Post Now", "🔄 Refresh"],
            ["📊 Stats", "📡 Channels"],
            ["➕ Add Channel", "📰 Add Blog"],
            ["💎 My Gemz", "💰 Buy Gemz"],
            ["⚙️ More", "❓ Help"],
        ],
        "resize_keyboard": True,
    }


def public_more_keyboard():
    return {
        "keyboard": [
            ["⏭️ Skip", "🧪 Test"],
            ["⏸️ My Channel Pause", "▶️ My Channel Resume"],
            ["🎁 Redeem Code", "📈 Estimate Usage"],
            ["🔗 My Referral Link", "🐛 Report Bug"],
            ["🗑️ Remove Channel"],
            ["⬅️ Back"],
        ],
        "resize_keyboard": True,
    }


def admin_keyboard():
    return {
        "keyboard": [
            ["▶️ Post Now", "🔄 Refresh"],
            ["📊 Stats", "📡 Channels"],
            ["⏸️ Pause", "▶️ Resume"],
            ["📢 Broadcast", "👥 Users"],
            ["⚙️ Advanced", "❓ Help"],
        ],
        "resize_keyboard": True,
    }


def advanced_keyboard():
    return {
        "keyboard": [
            ["⏭️ Skip", "🧪 Test"],
            ["💚 Health", "🐛 Report Bug"],
            ["💬 Message User", "📈 Estimate Usage"],
            ["🎟️ Generate Code", "💳 Credit User"],
            ["🔁 Manage Recurring Ads", "📣 Message All"],
            ["🔓 Unlock Channels", "🗑️ Reset History"],
            ["📜 Logs"],
            ["⬅️ Back"],
        ],
        "resize_keyboard": True,
    }


def cancel_only_keyboard():
    return {"keyboard": [["❌ Cancel"]], "resize_keyboard": True}


def force_join_keyboard():
    rows = []
    for c in FORCE_JOIN_CHATS:
        info = get_chat(f"@{c['username']}")
        title = info["result"]["title"] if info.get("ok") else c["label"]
        icon = "📢" if info.get("ok") and info["result"].get("type") == "channel" else "💬"
        rows.append([{"text": f"{icon} {title}", "url": c["url"]}])
    rows.append([{"text": "✅ I've Joined - Continue", "callback_data": "check_join"}])
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


def caption_format_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "✅ Use Default Format", "callback_data": "caption_default"}],
            [{"text": "✏️ Create My Own Format", "callback_data": "caption_custom"}],
        ]
    }


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


def send_join_gate(chat_id, first_name=None):
    greeting = f"👋 Hey {first_name}!" if first_name else "👋 Hey there!"
    send_message(
        chat_id,
        f"{greeting} Welcome to {BOT_NAME}.\n\n"
        f"Before we get started, please join the official Galaxy Gamez "
        f"channels and groups below - this keeps you in the loop on "
        f"updates, new features, and support. Once you've joined "
        f"everything, tap the button underneath to continue."
        + CREDITS_LINE,
        reply_markup=force_join_keyboard(),
    )


# ---------------- ADMIN CHECK ----------------

def is_admin(user_id):
    return str(user_id) == str(ADMIN_CHAT_ID)


# ---------------- COMMAND HANDLERS ----------------

def cmd_post(chat_id, user_id, users):
    from main import run_posting_cycle
    target_id = "__admin__" if is_admin(user_id) else str(user_id)
    u = get_user(users, target_id)

    if not is_admin(user_id):
        state = load_state()
        if state.get("paused"):
            send_message(chat_id, "⏸️ Posting is currently paused platform-wide by the team - Post Now is unavailable until it resumes. You'll be notified automatically when it's back.")
            return

    last_run = u.get("last_post_now_at")
    if last_run:
        elapsed = (datetime.utcnow() - datetime.fromisoformat(last_run)).total_seconds()
        if elapsed < POST_NOW_COOLDOWN_SECONDS:
            wait = int(POST_NOW_COOLDOWN_SECONDS - elapsed)
            send_message(chat_id, f"⏳ Still working through your last Post Now - try again in {wait}s. (This limit stops rapid taps from tying up the whole bot for everyone.)")
            return

    u["last_post_now_at"] = now_iso()
    send_message(chat_id, "Starting a posting cycle now (your channels only)...")
    results = run_posting_cycle(manual=True, only_user_id=target_id, users=users)
    send_message(chat_id, _format_post_results(results, users, target_id))


def _format_post_results(results, users, target_id):
    if not results:
        return "Done ✅ - nothing to post right now."

    by_channel = {}
    for line in results:
        channel_id, _, detail = line.partition(": ")
        by_channel.setdefault(channel_id, []).append(detail)

    u = get_user(users, target_id)
    channel_titles = {str(ch["channel_id"]): ch.get("title", "Channel") for ch in u.get("channels", [])}

    out = [box("POSTING COMPLETE")]
    total_ok = 0
    for channel_id, details in by_channel.items():
        title = channel_titles.get(channel_id, channel_id)
        out.append(f"\n📢 {title}")
        for d in details:
            if d.startswith("OK - "):
                out.append(f"  ✅ {d[5:]}")
                total_ok += 1
            elif d.startswith("FAILED"):
                out.append(f"  ❌ {d}")
            else:
                out.append(f"  ℹ️ {d}")
    out.append(f"\nTotal posted: {total_ok}")
    return "\n".join(out)


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
    send_message(chat_id, "Test message - the bot and command system are working.")


def cmd_channels(chat_id, user_id, users):
    u = get_user(users, user_id)
    if not u["channels"]:
        send_message(chat_id, "No channel added yet. Use ➕ Add Channel.")
        return
    lines = [box("YOUR CHANNELS"), ""]
    for i, ch in enumerate(u["channels"], start=1):
        r = get_chat(ch["channel_id"])
        if r.get("ok"):
            info = r["result"]
            title = info.get("title", "Untitled")
            username = f"@{info['username']}" if info.get("username") else "private, no username"
            lines.append(f"{i}. {title} ({username}) - ✅ reachable")
        else:
            lines.append(f"{i}. ID {ch['channel_id']} - ❌ {r.get('description', 'error')}")
    send_message(chat_id, "\n".join(lines))


def cmd_pause(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only. Use ⏸️ My Channel Pause to pause just your own channel.")
        return
    state = load_state()
    state["paused"] = True
    save_state(state)
    notified = 0
    for uid, u in users.items():
        if uid == "__admin__" or not u.get("channels"):
            continue
        send_message(
            uid,
            "⏸️ Auto-posting has been temporarily paused platform-wide by "
            "the team. Your setup is untouched and will resume automatically "
            "- no action needed from you.",
        )
        notified += 1
    send_message(chat_id, f"Global automatic posting paused for all users (your own channels keep running). Notified {notified} user(s).")


def cmd_resume(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    state = load_state()
    state["paused"] = False
    save_state(state)
    notified = 0
    for uid, u in users.items():
        if uid == "__admin__" or not u.get("channels"):
            continue
        send_message(uid, "▶️ Auto-posting is back up platform-wide. Your channels will resume on their normal schedule.")
        notified += 1
    send_message(chat_id, f"Global automatic posting resumed. Notified {notified} user(s).")


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
    real_users = {uid: u for uid, u in users.items() if uid != "__admin__"}
    lines = [f"CONNECTED USERS ({len(real_users)})"]
    for uid, u in real_users.items():
        info = get_chat(uid)
        if info.get("ok"):
            r = info["result"]
            username = f"@{r['username']}" if r.get("username") else "no username"
            name = " ".join(filter(None, [r.get("first_name"), r.get("last_name")])) or "no name"
            identity = f"{name} ({username}) - ID {uid}"
        else:
            identity = f"ID {uid} (profile lookup failed)"
        lines.append(
            f"{identity}: {len(u.get('channels', []))} channel(s), "
            f"strikes {u.get('strikes', 0)}/{STRIKE_LIMIT}, banned: {u.get('banned', False)}"
        )
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
            f"│ 📰 Add Blog — set your website/feed\n"
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

        )
    send_message(chat_id, text)


# ---------------- ONBOARDING: ADD CHANNEL / ADD BLOG ----------------

def cmd_remove_channel_start(chat_id, user_id, users):
    u = get_user(users, user_id)
    if not u["channels"]:
        send_message(chat_id, "You don't have any channels connected yet.")
        return
    rows = []
    for ch in u["channels"]:
        label = ch.get("title") or str(ch["channel_id"])
        rows.append([{"text": f"🗑️ {label}", "callback_data": f"rmchan_{ch['channel_id']}"}])
    send_message(chat_id, "Which channel do you want to remove? This stops all posting to it immediately.", reply_markup={"inline_keyboard": rows})


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
,
                )
            else:
                send_message(
                    chat_id,
                    f"You've reached the maximum of {MAX_CHANNELS_PAID} channels per account."
,
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
,
        reply_markup=cancel_only_keyboard(),
    )


def cmd_add_blog(chat_id, user_id, users):
    u = get_user(users, user_id)
    if not u["channels"]:
        send_message(chat_id, "Add your channel first with ➕ Add Channel.")
        return
    u["onboarding"]["step"] = "awaiting_blog"
    send_message(
        chat_id,
        "Send your website link - WordPress, Blogger, Medium, Ghost, or any "
        "RSS-enabled site all work. Just paste the normal site URL, we'll "
        "find your feed automatically.\n\ne.g. https://yourwebsite.com",
        reply_markup=cancel_only_keyboard(),
    )


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
            "caption_template": None,
            "last_posted_at": None,
            "created_at": now_iso(),
        })
        u["onboarding"]["step"] = None
        send_message(
            chat_id,
            "Channel connected ✅. Now tap 📰 Add Blog to set your website/feed.",
            reply_markup=keyboard_for(user_id),
        )
        return True

    if step == "awaiting_blog":
        text = message.get("text", "").strip()
        if len(text) < 4:
            send_message(chat_id, "That doesn't look like a website. Try again.")
            return True

        send_message(chat_id, "Checking your site for a feed, one moment...")
        feed_url = discover_feed(text)

        if not feed_url:
            send_message(
                chat_id,
                "Couldn't find a working feed on that site. Double-check the "
                "link, or if you already know your exact feed URL, paste that "
                "instead.",
            )
            return True

        u["channels"][-1]["blog_feed_url"] = feed_url
        u["onboarding"]["step"] = None
        send_message(
            chat_id,
            f"Feed found ✅ ({feed_url})\n\nNow, how should your posts look? "
            f"You can use our default clean format, or write your own.",
            reply_markup=caption_format_keyboard(),
        )
        return True

    if step == "awaiting_caption_template":
        text = message.get("text", "")
        if "{link}" not in text:
            send_message(
                chat_id,
                "Your format needs to include {link} somewhere so the post "
                "actually leads to your content. Try again - you can also "
                "use {title}.",
            )
            return True
        u["channels"][-1]["caption_template"] = text
        u["onboarding"]["step"] = None
        send_message(
            chat_id,
            "Format saved ✅. Last step - how often should this channel post?",
            reply_markup=schedule_unit_keyboard(),
        )
        return True

    return False


def chat_id_of_bot(u):
    return None  # placeholder, not required for getChatMember calls above


# ---------------- BROADCAST + STRIKE SYSTEM ----------------

def _send_broadcast_to_all_channels(users, content):
    """Sends the ad as ONE message per channel - a native quote-block
    '📢 ADVERTISEMENT' label at the top, followed by the original content
    with its formatting (bold/italic/links) preserved. Returns (sent, failed)."""
    broadcasts = load_broadcasts()
    sent, failed = 0, 0
    html = build_ad_html(content)

    for uid, target in users.items():
        for ch in target.get("channels", []):
            if content["kind"] == "photo":
                r = send_photo(ch["channel_id"], content["photo_file_id"], html, parse_mode="HTML")
            else:
                r = send_message(ch["channel_id"], html, parse_mode="HTML")

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
    return sent, failed


def cmd_broadcast_start(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    send_message(
        chat_id,
        "Send this once, or on a repeating schedule?",
        reply_markup={
            "inline_keyboard": [
                [{"text": "📤 Send Once", "callback_data": "broadcast_once"}],
                [{"text": "🔁 Repeat on a Schedule", "callback_data": "broadcast_recurring"}],
            ]
        },
    )


def handle_broadcast_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_broadcast":
        return False

    u["onboarding"]["step"] = None
    content = extract_message_content(message)
    sent, failed = _send_broadcast_to_all_channels(users, content)

    send_message(chat_id, f"Broadcast sent. Delivered: {sent}, Failed: {failed}", reply_markup=keyboard_for(user_id))
    return True


# ---------------- BUG REPORTS ----------------

def cmd_report_bug(chat_id, user_id, users):
    u = get_user(users, user_id)
    u["onboarding"]["step"] = "awaiting_bug_report"
    send_message(
        chat_id,
        "🐛 Describe the bug or issue you're facing - be as specific as possible "
        "(what you tapped, what you expected, what happened instead). "
        "It goes straight to the Galaxy Gamez team.",
        reply_markup=cancel_only_keyboard(),
    )


def handle_bug_report_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_bug_report":
        return False

    text = message.get("text", "")
    u["onboarding"]["step"] = None

    sender = message.get("from", {})
    username = f"@{sender['username']}" if sender.get("username") else "no username"
    name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])) or "no name"

    admin_note = (
        f"{box('BUG REPORT')}\n"
        f"From: {name} ({username}) - ID {user_id}\n\n"
        f"{text}"
    )
    send_message(ADMIN_CHAT_ID, admin_note)
    send_message(chat_id, "✅ Bug report sent - thanks for the heads up." + CREDITS_LINE, reply_markup=keyboard_for(user_id))
    return True


# ---------------- GEMZ: BALANCE, PURCHASE, PAYMENT PROOF ----------------

def cmd_my_gemz(chat_id, user_id, users):
    u = get_user(users, user_id)
    send_message(chat_id, f"💎 Your balance: {u.get('gemz_balance', 0)} Gemz")


def cmd_buy_gemz(chat_id, user_id, users):
    if not GEMZ_PACKAGES:
        send_message(chat_id, "Plans aren't set up yet - check back soon.")
        return

    send_message(
        chat_id,
        f"{box('GEMZ PLANS')}\n\n"
        f"Pick the plan that fits how you post. Not sure? Try 📈 Estimate "
        f"Usage first to see exactly how long each option realistically "
        f"lasts for your setup.",
        reply_markup=gemz_plans_keyboard(),
    )


def gemz_plans_keyboard():
    rows = []
    for i, p in enumerate(GEMZ_PACKAGES):
        rows.append([{
            "text": f"{p['label']} - {p['gemz']:,} Gemz (₦{p['price_naira']:,})",
            "callback_data": f"buy_plan_{i}",
        }])
    return {"inline_keyboard": rows}


def handle_payment_proof_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_payment_proof":
        return False
    if not message.get("photo"):
        return False  # wait for an actual photo, ignore other text in the meantime

    u["onboarding"]["step"] = None
    order_code = u["onboarding"].get("pending_order_code")
    order_line = ""
    if order_code:
        orders = load_orders()
        order = next((o for o in orders if o["order_code"] == order_code), None)
        if order:
            order_line = (
                f"\nOrder: {order_code} - {order['plan_label']} "
                f"({order['gemz']:,} Gemz, ₦{order['price_naira']:,})\n"
            )

    forward_message(ADMIN_CHAT_ID, chat_id, message["message_id"])
    send_message(
        ADMIN_CHAT_ID,
        f"👆 Payment screenshot from user {user_id}.{order_line}\n"
        f"Reply to them anytime with 💬 Message User - use 💳 Credit User once confirmed.",
    )
    send_message(chat_id, "✅ Payment received and passed on to our team for verification. We'll credit your Gemz shortly and let you know as soon as it's done - thanks for your patience.", reply_markup=keyboard_for(user_id))
    return True


# ---------------- ADMIN: CREDIT USER / UNLOCK CHANNEL SLOTS ----------------

def cmd_credit_start(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    u = get_user(users, user_id)
    u["onboarding"]["step"] = "awaiting_credit"
    send_message(chat_id, "Send: <user_id> <gemz_amount>  e.g. 123456789 5000", reply_markup=cancel_only_keyboard())


def handle_credit_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_credit":
        return False
    u["onboarding"]["step"] = None

    parts = message.get("text", "").split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        send_message(chat_id, "Format: <user_id> <amount>  e.g. 123456789 5000", reply_markup=cancel_only_keyboard())
        u["onboarding"]["step"] = "awaiting_credit"
        return True

    target_id, amount = parts[0], int(parts[1])
    target = get_user(users, target_id)
    target["gemz_balance"] = target.get("gemz_balance", 0) + amount
    send_message(chat_id, f"✅ Credited {amount} Gemz to {target_id}. New balance: {target['gemz_balance']}", reply_markup=keyboard_for(user_id))
    send_message(target_id, f"💎 {amount} Gemz added to your balance by the team.")
    apply_referral_purchase_bonus(users, target_id, amount)
    return True


def cmd_reset_terms(chat_id, user_id, users, args_text):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    target_id = args_text.strip()
    if not target_id.isdigit():
        send_message(chat_id, "Usage: /resetterms <user_id>")
        return
    target = get_user(users, target_id)
    target["terms_accepted"] = False
    send_message(chat_id, f"✅ Terms reset for {target_id} - they'll see the ToS prompt again next message.")


def cmd_unlock_slots_start(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    u = get_user(users, user_id)
    u["onboarding"]["step"] = "awaiting_unlock_slots"
    send_message(chat_id, f"Send the user ID to raise their channel limit to {MAX_CHANNELS_PAID}.", reply_markup=cancel_only_keyboard())


def handle_unlock_slots_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_unlock_slots":
        return False
    u["onboarding"]["step"] = None
    cmd_unlock_slots(chat_id, user_id, users, message.get("text", ""))
    send_message(chat_id, "Done.", reply_markup=keyboard_for(user_id))
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
    send_message(target_id, f"🔓 Your account can now connect up to {MAX_CHANNELS_PAID} channels.")


# ---------------- REDEEM CODES ----------------

def _generate_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def _generate_order_code():
    return "GGZ-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def cmd_gencode_start(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    u = get_user(users, user_id)
    u["onboarding"]["step"] = "awaiting_gencode"
    send_message(chat_id, "Send: <user_id> <gemz_amount>  e.g. 123456789 500", reply_markup=cancel_only_keyboard())


def handle_gencode_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_gencode":
        return False
    u["onboarding"]["step"] = None

    parts = message.get("text", "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        send_message(chat_id, "Format: <user_id> <amount>  e.g. 123456789 500", reply_markup=cancel_only_keyboard())
        u["onboarding"]["step"] = "awaiting_gencode"
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
            reply_markup=keyboard_for(user_id),
        )
        return True

    code = _generate_code()
    codes.append({
        "code": code, "user_id": target_id, "amount": amount,
        "used": False, "created_at": now_iso(),
    })
    save_redeem_codes(codes)
    send_message(chat_id, f"✅ Code generated for {target_id}: {code} (worth {amount} Gemz). Send it to them directly.", reply_markup=keyboard_for(user_id))
    return True


def cmd_redeem_start(chat_id, user_id, users):
    u = get_user(users, user_id)
    u["onboarding"]["step"] = "awaiting_redeem"
    send_message(chat_id, "🎁 Enter your redeem code:", reply_markup=cancel_only_keyboard())


def handle_redeem_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_redeem":
        return False
    u["onboarding"]["step"] = None

    entered = message.get("text", "").strip().upper()
    codes = load_redeem_codes()
    match = next((c for c in codes if c["code"] == entered and c["user_id"] == str(user_id)), None)

    if not match:
        send_message(chat_id, "❌ Invalid code, or this code isn't assigned to you.", reply_markup=keyboard_for(user_id))
        return True
    if match["used"]:
        send_message(chat_id, "❌ This code has already been used and can't be redeemed again.", reply_markup=keyboard_for(user_id))
        return True

    match["used"] = True
    save_redeem_codes(codes)
    u["gemz_balance"] = u.get("gemz_balance", 0) + match["amount"]
    send_message(chat_id, f"✅ Redeemed! +{match['amount']} Gemz. New balance: {u['gemz_balance']}", reply_markup=keyboard_for(user_id))
    return True


# ---------------- USAGE ESTIMATOR ----------------

def handle_budget_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_budget_naira":
        return False

    text = message.get("text", "").strip().replace(",", "").replace("₦", "")
    u["onboarding"]["step"] = None

    if not text.isdigit():
        send_message(chat_id, "That doesn't look like a plain number. Try again, e.g. 7000.")
        u["onboarding"]["step"] = "awaiting_budget_naira"
        return True

    naira = int(text)
    gemz = naira // NAIRA_PER_GEMZ

    est = u["onboarding"].get("last_estimate")
    if not est:
        send_message(
            chat_id,
            f"₦{naira:,} gets you {gemz:,} Gemz at the current rate. Run 📈 Estimate "
            f"Usage first to see exactly how long that lasts for your setup.",
        )
        return True

    d = estimate_days(gemz, est["channels"], est["interval_hours"], est["posts_per_cycle"])
    interval_hours = est["interval_hours"]
    interval_label = f"{interval_hours}hr" if interval_hours < 24 else f"{interval_hours // 24} day(s)"
    send_message(
        chat_id,
        f"{box('BUDGET RESULT')}\n\n"
        f"₦{naira:,} = {gemz:,} Gemz\n"
        f"For {est['channels']} channel(s), {est['posts_per_cycle']} post(s) every {interval_label}:\n\n"
        f"➜ Lasts: {format_duration(d)}",
        reply_markup=keyboard_for(user_id),
    )
    return True


# ---------------- REFERRALS ----------------

def complete_referral_if_eligible(users, new_user_id):
    """Called once a new user finishes fully setting up their first
    channel (website + channel connected). If they arrived via a referral
    link, this just CONFIRMS the referral - no Gemz changes hands yet:
      - The referred user's 24hr trial starts later, at their first actual
        scheduled post (see grant_trial_if_first_post in main.py).
      - The referrer's reward is a lifetime 5% of every future Gemz
        purchase the referred user makes (see apply_referral_purchase_bonus),
        not a one-time bonus."""
    new_user_id = str(new_user_id)
    u = get_user(users, new_user_id)
    referrer_id = u.get("referred_by")
    if not referrer_id or u.get("referral_completed"):
        return

    u["referral_completed"] = True
    u["trial_started_at"] = None
    u["trial_bonus_given"] = False

    send_message(
        referrer_id,
        f"🎉 Your referral connected their first channel! You'll now earn "
        f"5% of every Gemz purchase they ever make, for life.",
    )
    send_message(
        new_user_id,
        f"🎉 You're all set. Your 24-hour free trial starts once your first "
        f"post goes out - after that, you'll get 500 free Gemz to keep going."
        + CREDITS_LINE,
    )


def apply_referral_purchase_bonus(users, buyer_user_id, gemz_purchased):
    """Called every time a user is credited Gemz for a genuine PAID
    purchase (admin Credit User command). If they were referred, their
    referrer gets 5% of that amount, forever - not a one-time thing.
    Does NOT apply to redeem codes, the 500-Gemz trial-end bonus, or any
    other non-purchase credit."""
    buyer_user_id = str(buyer_user_id)
    u = get_user(users, buyer_user_id)
    referrer_id = u.get("referred_by")
    if not referrer_id or not u.get("referral_completed"):
        return

    bonus = round(gemz_purchased * 0.05)
    if bonus <= 0:
        return

    referrer = get_user(users, referrer_id)
    referrer["gemz_balance"] = referrer.get("gemz_balance", 0) + bonus
    send_message(
        referrer_id,
        f"💎 Your referral just bought Gemz - you earned {bonus} Gemz "
        f"(5% referral bonus).",
    )


def cmd_my_referral(chat_id, user_id, users):
    link = f"https://t.me/{BOT_USERNAME}?start=REF{user_id}"
    u = get_user(users, user_id)
    referred_count = sum(
        1 for other in users.values()
        if other.get("referred_by") == str(user_id) and other.get("referral_completed")
    )
    send_message(
        chat_id,
        f"{box('MY REFERRAL LINK')}\n\n"
        f"{link}\n\n"
        f"How it works: once someone joins through your link, joins the "
        f"required channels, and connects their first channel, they get a "
        f"24-hour free trial followed by 500 free Gemz to get started - and "
        f"you earn 5% of every Gemz purchase they ever make, for as long as "
        f"they're active. No limit on how many people you refer.\n\n"
        f"Completed referrals so far: {referred_count}",
    )
    send_message(
        chat_id,
        f"Want an easy message to send them? Copy the text below and share "
        f"it directly:\n\n"
        f"---\n"
        f"🎮 I've been using this bot to auto-post to my Telegram channel "
        f"straight from my website - no manual posting needed. It works "
        f"with WordPress, Blogger, Medium, Ghost, or basically any site "
        f"with an RSS feed.\n\n"
        f"You get a free 24-hour trial + 500 free Gemz just for trying it "
        f"out. Thought you'd like it too:\n"
        f"{link}\n"
        f"---",
    )


def cmd_message_all_start(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    u = get_user(users, user_id)
    u["onboarding"]["step"] = "awaiting_message_all"
    send_message(chat_id, "Send the message now - it goes to every registered user's DM (not their channels).", reply_markup=cancel_only_keyboard())


def handle_message_all_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_message_all":
        return False

    u["onboarding"]["step"] = None
    text = message.get("text", "")
    if not text:
        send_message(chat_id, "Send text only for now.", reply_markup=cancel_only_keyboard())
        u["onboarding"]["step"] = "awaiting_message_all"
        return True

    sent = 0
    for uid in users:
        if uid == "__admin__":
            continue
        r = send_message(uid, f"📣 Message from the Galaxy Gamez team:\n\n{text}")
        if r.get("ok"):
            sent += 1
    send_message(chat_id, f"✅ Sent to {sent} user(s).", reply_markup=keyboard_for(user_id))
    return True


def cmd_message_user_start(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    u = get_user(users, user_id)
    u["onboarding"]["step"] = "awaiting_msguser_id"
    send_message(chat_id, "Who do you want to message? Send their user ID.", reply_markup=cancel_only_keyboard())


def handle_msguser_id_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_msguser_id":
        return False
    target_id = message.get("text", "").strip()
    if not target_id.isdigit():
        send_message(chat_id, "That doesn't look like a user ID. Try again.", reply_markup=cancel_only_keyboard())
        return True
    u["onboarding"]["msg_target"] = target_id
    u["onboarding"]["step"] = "awaiting_msguser_text"
    send_message(
        chat_id,
        f"Send your message to {target_id} now. You can send as many "
        f"messages as you like - tap ❌ Cancel when you're done.",
        reply_markup=cancel_only_keyboard(),
    )
    return True


def handle_msguser_text_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_msguser_text":
        return False
    target_id = u["onboarding"].get("msg_target")
    text = message.get("text", "")
    if not text:
        send_message(chat_id, "Send text only for now.", reply_markup=cancel_only_keyboard())
        return True
    send_message(target_id, f"💬 Message from the Galaxy Gamez team:\n\n{text}")
    send_message(chat_id, f"✅ Sent to {target_id}. Send another, or tap ❌ Cancel when done.", reply_markup=cancel_only_keyboard())
    return True


def handle_recurring_broadcast_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_recurring_broadcast":
        return False

    interval_hours = u["onboarding"].get("recurring_interval_hours", 24)
    u["onboarding"]["step"] = None

    scheduled = load_scheduled_broadcasts()
    scheduled.append({
        "id": _generate_code(),
        "content": extract_message_content(message),
        "interval_hours": interval_hours,
        "next_run": now_iso(),
        "created_at": now_iso(),
        "active": True,
    })
    save_scheduled_broadcasts(scheduled)

    send_message(
        chat_id,
        f"✅ Recurring ad scheduled - repeats every {interval_hours}hr, "
        f"starting now. Manage or stop it anytime from ⚙️ Advanced → 🔁 Manage Recurring Ads.",
        reply_markup=keyboard_for(user_id),
    )
    return True


def cmd_manage_recurring(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    scheduled = load_scheduled_broadcasts()
    active = [s for s in scheduled if s.get("active")]
    if not active:
        send_message(chat_id, "No recurring ads running right now. Set one up from 📢 Broadcast → 🔁 Repeat on a Schedule.")
        return

    lines = [box("RECURRING ADS")]
    rows = []
    for s in active:
        lines.append(f"\nID {s['id']} - every {s['interval_hours']}hr - next run: {s['next_run']}")
        rows.append([{"text": f"🛑 Stop {s['id']}", "callback_data": f"stop_recurring_{s['id']}"}])
    send_message(chat_id, "\n".join(lines), reply_markup={"inline_keyboard": rows})


def run_scheduled_broadcasts(users):
    """Checked every poll cycle. Fires any recurring broadcast that's due,
    then reschedules it for the next interval. Returns True if anything
    changed, for the caller's save decision."""
    scheduled = load_scheduled_broadcasts()
    changed = False

    for s in scheduled:
        if not s.get("active"):
            continue
        if datetime.utcnow() < datetime.fromisoformat(s["next_run"]):
            continue

        _send_broadcast_to_all_channels(users, s["content"])
        s["next_run"] = (datetime.utcnow() + timedelta(hours=s["interval_hours"])).isoformat()
        changed = True

    if changed:
        save_scheduled_broadcasts(scheduled)
    return changed


def cmd_estimate_start(chat_id, user_id, users):
    u = get_user(users, user_id)
    u["onboarding"]["estimate"] = {}
    send_message(chat_id, "📈 How many channels are you running?", reply_markup=estimate_channels_keyboard())


def apply_daily_upkeep(users):
    """Charges GEMZ_COST_PER_CHANNEL_PER_DAY per active channel, once per
    calendar day per user. Admin and users in an active free trial are
    exempt. Auto-pauses channels if the balance can't cover the charge.
    Returns True if anything changed, for the caller's save decision."""
    from main import _is_in_free_trial
    today = date.today().isoformat()
    any_changed = False

    for uid, u in users.items():
        if uid == "__admin__" or not u.get("channels"):
            continue
        if u.get("last_upkeep_date") == today:
            continue  # already charged today
        if _is_in_free_trial(u):
            u["last_upkeep_date"] = today
            any_changed = True
            continue

        active_channels = [c for c in u["channels"] if not c.get("paused")]
        if not active_channels:
            u["last_upkeep_date"] = today
            continue

        charge = len(active_channels) * GEMZ_COST_PER_CHANNEL_PER_DAY
        u["last_upkeep_date"] = today
        any_changed = True

        if u.get("gemz_balance", 0) >= charge:
            u["gemz_balance"] -= charge
        else:
            # Can't cover it - pause everything and let them know
            for c in active_channels:
                c["paused"] = True
            send_message(
                uid,
                f"⏸️ Your channel(s) have been paused - your Gemz balance "
                f"couldn't cover today's upkeep. Top up with 💰 Buy Gemz to "
                f"resume.",
            )

    return any_changed


def check_inactive_and_broken_users(users):
    """Run once per day per user (throttled via last_nudge_check_date).
    Nudges two situations, at most one message every few days per user
    so it never feels spammy:
      - Broken setup: a channel was added 2+ days ago and has never
        successfully posted (feed might be wrong/dead).
      - Inactive: no interaction with the bot in 7+ days.
    Returns True if anything changed, for the caller's save decision."""
    today = date.today().isoformat()
    any_changed = False

    for uid, u in users.items():
        if uid == "__admin__":
            continue
        if u.get("last_nudge_check_date") == today:
            continue
        u["last_nudge_check_date"] = today
        any_changed = True

        last_nudge = u.get("last_nudge_sent_at")
        if last_nudge and (datetime.utcnow() - datetime.fromisoformat(last_nudge)) < timedelta(days=4):
            continue  # nudged recently, don't pile on

        broken_channels = []
        for ch in u.get("channels", []):
            created = ch.get("created_at")
            if not created or ch.get("last_posted_at") or ch.get("paused"):
                continue
            age = datetime.utcnow() - datetime.fromisoformat(created)
            if age > timedelta(days=2):
                broken_channels.append(ch)

        if broken_channels:
            send_message(
                uid,
                f"👋 Noticed your channel hasn't posted anything yet since you "
                f"connected it a couple days ago - that usually means the "
                f"website/feed link needs a second look. Try 🔄 Refresh to "
                f"check it, or {SUPPORT_HANDLE} if you're stuck." + CREDITS_LINE,
            )
            u["last_nudge_sent_at"] = now_iso()
            continue  # one nudge type per check is enough

        last_seen = u.get("last_seen_at")
        if u.get("channels") and last_seen:
            inactive_for = datetime.utcnow() - datetime.fromisoformat(last_seen)
            if inactive_for > timedelta(days=7):
                send_message(
                    uid,
                    f"👋 Haven't seen you in a while - your channel is still "
                    f"running in the background. Pop in anytime to check "
                    f"📊 Stats or 💎 My Gemz." + CREDITS_LINE,
                )
                u["last_nudge_sent_at"] = now_iso()

    return any_changed


def check_referral_trials(users):
    """Run every cycle alongside check_broadcast_strikes. Once a referred
    user's 24hr trial (started at their first real post) has elapsed,
    grant the one-time 500 Gemz starter bonus - this is NOT a purchase,
    so it does NOT trigger the referrer's 5% bonus. Returns True if any
    balance was changed, so the caller knows to save/push regardless of
    whether there were any incoming Telegram messages this cycle."""
    any_changed = False
    for uid, u in users.items():
        if not u.get("referred_by") or not u.get("referral_completed"):
            continue
        if u.get("trial_bonus_given") or not u.get("trial_started_at"):
            continue
        started = datetime.fromisoformat(u["trial_started_at"])
        if datetime.utcnow() - started < timedelta(hours=24):
            continue
        u["gemz_balance"] = u.get("gemz_balance", 0) + 500
        u["trial_bonus_given"] = True
        any_changed = True
        send_message(
            uid,
            "🎁 Your 24-hour trial has ended - 500 free Gemz added to your "
            "balance to keep you going. Top up anytime with 💰 Buy Gemz."
,
        )
    return any_changed


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

        uid = b["user_id"]
        if uid == "__admin__":
            continue  # admin's own channels are never subject to strikes/bans

        if not message_still_exists(b["channel_id"], b["message_id"]):
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
    return changed


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
    "💬 Message User": cmd_message_user_start, "/messageuser": cmd_message_user_start,
    "/help": cmd_help, "❓ Help": cmd_help,
    "➕ Add Channel": cmd_add_channel,
    "📰 Add Blog": cmd_add_blog,
    "📢 Broadcast": cmd_broadcast_start,
    "/reportbug": cmd_report_bug, "🐛 Report Bug": cmd_report_bug,
    "💎 My Gemz": cmd_my_gemz, "/mygemz": cmd_my_gemz,
    "💰 Buy Gemz": cmd_buy_gemz, "/buygemz": cmd_buy_gemz,
    "🎁 Redeem Code": cmd_redeem_start, "/redeem": cmd_redeem_start,
    "📈 Estimate Usage": cmd_estimate_start, "/estimate": cmd_estimate_start,
    "🔗 My Referral Link": cmd_my_referral, "/referral": cmd_my_referral,
    "🎟️ Generate Code": cmd_gencode_start,
    "🔁 Manage Recurring Ads": cmd_manage_recurring, "/manageads": cmd_manage_recurring,
    "📣 Message All": cmd_message_all_start, "/messageall": cmd_message_all_start,
    "🔓 Unlock Channels": cmd_unlock_slots_start,
    "🗑️ Remove Channel": cmd_remove_channel_start,
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
        print(f"Force-join check for {user_id}: missing={[c['username'] for c in missing]}")
        if missing:
            send_join_gate(chat_id, message["from"].get("first_name"))
            return

    u = get_user(users, user_id)
    if not is_admin(user_id):
        u["last_seen_at"] = now_iso()
    if not is_admin(user_id) and not u.get("terms_accepted"):
        send_message(chat_id, TERMS_TEXT, reply_markup=terms_keyboard())
        return

    text = message.get("text", "").strip()

    if text == "❌ Cancel":
        u["onboarding"]["step"] = None
        u["onboarding"]["estimate"] = {}
        send_message(chat_id, "Cancelled.", reply_markup=keyboard_for(user_id))
        return

    if text.startswith("/unlockchannels"):
        cmd_unlock_slots(chat_id, user_id, users, text[len("/unlockchannels"):])
        return

    if text.startswith("/resetterms"):
        cmd_reset_terms(chat_id, user_id, users, text[len("/resetterms"):])
        return

    if text == "⚙️ Advanced" and is_admin(user_id):
        send_message(chat_id, "Advanced menu:", reply_markup=advanced_keyboard())
        return
    if text == "⚙️ More" and not is_admin(user_id):
        send_message(chat_id, "More options:", reply_markup=public_more_keyboard())
        return
    if text == "⬅️ Back":
        send_message(chat_id, "Main menu:", reply_markup=keyboard_for(user_id))
        return
    if text == "/start" or text.startswith("/start "):
        u = get_user(users, user_id)
        parts = text.split(maxsplit=1)
        if len(parts) == 2 and parts[1].startswith("REF") and not u.get("referred_by"):
            referrer_id = parts[1][3:]
            if referrer_id != user_id and referrer_id in users:
                u["referred_by"] = referrer_id

        welcome = (
            f"❏ {BOT_NAME}\n\n"
            f"I auto-post fresh content from your website straight to your "
            f"Telegram channel, on your own schedule. Works with WordPress, "
            f"Blogger, Medium, Ghost, or any RSS-enabled site — connect your "
            f"channel + website and I take it from there.\n\n"
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
    if handle_budget_message(chat_id, user_id, users, message):
        return
    if handle_recurring_broadcast_message(chat_id, user_id, users, message):
        return
    if handle_message_all_message(chat_id, user_id, users, message):
        return
    if handle_unlock_slots_message(chat_id, user_id, users, message):
        return
    if handle_msguser_id_message(chat_id, user_id, users, message):
        return
    if handle_msguser_text_message(chat_id, user_id, users, message):
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
            u = get_user(users, user_id)
            if not is_admin(user_id) and not u.get("terms_accepted"):
                send_message(chat_id, TERMS_TEXT, reply_markup=terms_keyboard())
            else:
                send_message(chat_id, "Access unlocked ✅ Welcome!", reply_markup=keyboard_for(user_id))
        return

    if data == "caption_default":
        u = get_user(users, user_id)
        if not u["channels"]:
            answer_callback(callback["id"], "No channel found - start over with Add Channel.")
            return
        u["channels"][-1]["caption_template"] = None
        answer_callback(callback["id"], "Default format set ✅")
        send_message(
            chat_id,
            "Default format set ✅. Last step - how often should this channel post?",
            reply_markup=schedule_unit_keyboard(),
        )
        return

    if data == "caption_custom":
        u = get_user(users, user_id)
        if not u["channels"]:
            answer_callback(callback["id"], "No channel found - start over with Add Channel.")
            return
        u["onboarding"]["step"] = "awaiting_caption_template"
        answer_callback(callback["id"])
        send_message(
            chat_id,
            "Type your own post format. Use {title} and {link} anywhere you "
            "want them to appear - {link} is required.\n\n"
            "Example:\n📢 {title}\n\nRead more: {link}",
            reply_markup=cancel_only_keyboard(),
        )
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
            f"All set ✅ Your channel will post {n} game(s) every {interval_label}.",
            reply_markup=keyboard_for(user_id),
        )
        complete_referral_if_eligible(users, user_id)
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
        answer_callback(callback["id"])

        if not channels or not interval_hours:
            u["onboarding"]["estimate"] = {}
            send_message(chat_id, "Something went wrong - start over with 📈 Estimate Usage.")
            return

        # Remember this setup so "I Have A Budget" can reuse it without re-asking
        u["onboarding"]["last_estimate"] = {
            "channels": channels, "interval_hours": interval_hours, "posts_per_cycle": n,
        }
        u["onboarding"]["estimate"] = {}

        interval_label = f"{interval_hours}hr" if interval_hours < 24 else f"{interval_hours // 24} day(s)"
        lines = [
            box("USAGE ESTIMATE"),
            "",
            f"Setup: {channels} channel(s), {n} post(s) every {interval_label}",
            "",
        ]
        for p in GEMZ_PACKAGES:
            d = estimate_days(p["gemz"], channels, interval_hours, n)
            lines.append(f"{p['label']} ({p['gemz']:,} Gemz, ₦{p['price_naira']:,}): {format_duration(d)}")
        lines.append("")
        lines.append("Have a specific budget instead? Tap 💰 I Have A Budget below.")

        send_message(
            chat_id,
            "\n".join(lines),
            reply_markup={"inline_keyboard": [[{"text": "💰 I Have A Budget (₦)", "callback_data": "enter_budget"}]]},
        )
        return

    if data.startswith("rmchan_"):
        target_channel_id = int(data[len("rmchan_"):])
        u = get_user(users, user_id)
        before = len(u["channels"])
        u["channels"] = [c for c in u["channels"] if c["channel_id"] != target_channel_id]
        if len(u["channels"]) < before:
            answer_callback(callback["id"], "Removed.")
            send_message(chat_id, f"✅ Channel removed. It will no longer receive posts.", reply_markup=keyboard_for(user_id))
        else:
            answer_callback(callback["id"], "Not found.")
        return

    if data.startswith("buy_plan_"):
        idx = int(data.rsplit("_", 1)[1])
        if idx >= len(GEMZ_PACKAGES):
            answer_callback(callback["id"], "That plan isn't available anymore.")
            return
        plan = GEMZ_PACKAGES[idx]
        answer_callback(callback["id"])

        order_code = _generate_order_code()
        orders = load_orders()
        orders.append({
            "order_code": order_code,
            "user_id": user_id,
            "plan_label": plan["label"],
            "gemz": plan["gemz"],
            "price_naira": plan["price_naira"],
            "status": "pending",
            "created_at": now_iso(),
        })
        save_orders(orders)

        u = get_user(users, user_id)
        u["onboarding"]["step"] = "awaiting_payment_proof"
        u["onboarding"]["pending_order_code"] = order_code

        send_message(
            chat_id,
            f"{box('COMPLETE YOUR PAYMENT')}\n\n"
            f"Plan: {plan['label']} ({plan['gemz']:,} Gemz)\n"
            f"Amount: ₦{plan['price_naira']:,}\n\n"
            f"Bank: {PAYMENT_INFO['bank_name']}\n"
            f"Account name: {PAYMENT_INFO['account_name']}\n"
            f"Account number: `{PAYMENT_INFO['account_number']}`\n\n"
            f"⚠️ Important: add this order code to the transfer description/"
            f"narration so your payment can be matched instantly:\n"
            f"`{order_code}`\n\n"
            f"Once paid, send the payment screenshot here as a photo - it "
            f"goes straight to the team. You'll be credited once confirmed."
,
            reply_markup=cancel_only_keyboard(),
            parse_mode="Markdown",
        )
        return

    if data == "broadcast_once":
        answer_callback(callback["id"])
        u = get_user(users, user_id)
        u["onboarding"]["step"] = "awaiting_broadcast"
        send_message(chat_id, "Send the promo/ad text now. It will go to every connected channel.", reply_markup=cancel_only_keyboard())
        return

    if data == "broadcast_recurring":
        answer_callback(callback["id"])
        send_message(
            chat_id,
            "How often should this repeat?",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "Every 6 hours", "callback_data": "bcast_int_6"}],
                    [{"text": "Every 12 hours", "callback_data": "bcast_int_12"}],
                    [{"text": "Every 24 hours", "callback_data": "bcast_int_24"}],
                    [{"text": "Every 3 days", "callback_data": "bcast_int_72"}],
                    [{"text": "Every 7 days", "callback_data": "bcast_int_168"}],
                ]
            },
        )
        return

    if data.startswith("bcast_int_"):
        interval_hours = int(data.rsplit("_", 1)[1])
        answer_callback(callback["id"])
        u = get_user(users, user_id)
        u["onboarding"]["step"] = "awaiting_recurring_broadcast"
        u["onboarding"]["recurring_interval_hours"] = interval_hours
        send_message(
            chat_id,
            f"Send the promo/ad content now - it'll repeat every "
            f"{interval_hours}hr automatically to every connected channel "
            f"until you stop it (⚙️ Advanced → 🔁 Manage Recurring Ads).",
            reply_markup=cancel_only_keyboard(),
        )
        return

    if data.startswith("stop_recurring_"):
        stop_id = data[len("stop_recurring_"):]
        scheduled = load_scheduled_broadcasts()
        for s in scheduled:
            if s["id"] == stop_id:
                s["active"] = False
        save_scheduled_broadcasts(scheduled)
        answer_callback(callback["id"], "Stopped.")
        send_message(chat_id, f"🛑 Recurring ad {stop_id} stopped.")
        return

    if data == "enter_budget":
        u = get_user(users, user_id)
        u["onboarding"]["step"] = "awaiting_budget_naira"
        answer_callback(callback["id"])
        send_message(
            chat_id,
            "How much can you spend? Send a Naira amount (numbers only, e.g. 7000).",
            reply_markup=cancel_only_keyboard(),
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
