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
    check_broadcast_strikes, check_referral_trials, apply_daily_upkeep,
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
                _last_alive["ts"] = time.time()  # proof of life per-update, not just per-batch - a big backlog can legitimately take a while
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

                # Save both state AND users after EVERY update, not just at
                # the end of the batch - these are cheap local writes (no
                # git push yet), but they mean a watchdog restart mid-backlog
                # can never lose track of what was already sent (which would
                # otherwise risk duplicate posts) or reprocess handled
                # messages.
                save_state(state)
                save_users(users)

            strikes_changed = check_broadcast_strikes(users)
            trials_changed = check_referral_trials(users)
            upkeep_changed = apply_daily_upkeep(users)

            if changed or updates or strikes_changed or trials_changed or upkeep_changed:
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

def cmd_broadcast_start(chat_id, user_id, users):
    if not is_admin(user_id):
        send_message(chat_id, "Admin only.")
        return
    u = get_user(users, user_id)
    u["onboarding"]["step"] = "awaiting_broadcast"
    send_message(chat_id, "Send the promo/ad text now. It will go to every connected channel.", reply_markup=cancel_only_keyboard())


def handle_broadcast_message(chat_id, user_id, users, message):
    u = get_user(users, user_id)
    if u["onboarding"].get("step") != "awaiting_broadcast":
        return False

    u["onboarding"]["step"] = None
    broadcasts = load_broadcasts()
    sent, failed = 0, 0
    source_chat_id = message["chat"]["id"]
    source_message_id = message["message_id"]

    for uid, target in users.items():
        for ch in target.get("channels", []):
            r = copy_message(ch["channel_id"], source_chat_id, source_message_id)
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
