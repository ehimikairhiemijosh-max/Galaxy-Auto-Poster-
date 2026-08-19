"""
Galaxy Gamez - Telegram API wrapper
Plain HTTP requests only, every call checked against Telegram's "ok" field.
"""

import time
import requests

from config import API_BASE, RETRY_ATTEMPTS


def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = _json(reply_markup)
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return _post("sendMessage", payload)


def send_photo(chat_id, photo_url, caption, reply_markup=None, parse_mode=None):
    payload = {"chat_id": chat_id, "photo": photo_url, "caption": caption}
    if reply_markup:
        payload["reply_markup"] = _json(reply_markup)
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return _post("sendPhoto", payload)


def send_once(channel_id, image_url, caption):
    """Used by the posting engine. Returns (success, message, sent_message_id)."""
    if image_url:
        data = send_photo(channel_id, image_url, caption)
    else:
        data = send_message(channel_id, caption)
    if data.get("ok"):
        return True, "Sent", data["result"]["message_id"]
    return False, data.get("description", "Unknown Telegram error"), None


def send_with_retry(channel_id, image_url, caption):
    delay = 1
    last_message = ""
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        success, message, msg_id = send_once(channel_id, image_url, caption)
        if success:
            return True, message, msg_id
        last_message = message
        if attempt < RETRY_ATTEMPTS:
            time.sleep(delay)
            delay *= 2
    return False, last_message, None


def get_chat_member(chat_id_or_username, user_id):
    try:
        resp = requests.get(
            f"{API_BASE}/getChatMember",
            params={"chat_id": chat_id_or_username, "user_id": user_id},
            timeout=15,
        )
        return resp.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


def get_chat(chat_id_or_username):
    try:
        resp = requests.get(
            f"{API_BASE}/getChat",
            params={"chat_id": chat_id_or_username},
            timeout=15,
        )
        return resp.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


def message_still_exists(chat_id, message_id):
    """Telegram has no 'get message' call, so we attempt a no-op edit.
    If it fails with 'message to edit not found' / 'message can't be edited'
    because it's gone, we know it was deleted."""
    try:
        resp = requests.post(
            f"{API_BASE}/editMessageReplyMarkup",
            data={"chat_id": chat_id, "message_id": message_id},
            timeout=15,
        )
        data = resp.json()
    except Exception:
        return True  # network hiccup - don't punish the user for our failure

    if data.get("ok"):
        return True
    desc = (data.get("description") or "").lower()
    if "not found" in desc or "message to edit not found" in desc or "message can't be edited" in desc:
        return False
    return True  # any other error (rate limit etc) - assume still there


def forward_message(to_chat_id, from_chat_id, message_id):
    return _post("forwardMessage", {
        "chat_id": to_chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
    })


def copy_message(to_chat_id, from_chat_id, message_id):
    """Copies a message to another chat WITHOUT the 'Forwarded from' label,
    preserving all formatting (bold, italics, quotes, links) exactly as
    typed - unlike manually re-sending plain .text, which strips every
    bit of Telegram-native formatting."""
    return _post("copyMessage", {
        "chat_id": to_chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
    })


def get_updates(offset):
    try:
        resp = requests.get(
            f"{API_BASE}/getUpdates",
            params={"offset": offset, "timeout": 0},
            timeout=30,
        )
        return resp.json().get("result", [])
    except Exception as e:
        print(f"Failed to get updates: {e}")
        return []


def answer_callback(callback_query_id, text=""):
    try:
        requests.post(
            f"{API_BASE}/answerCallbackQuery",
            data={"callback_query_id": callback_query_id, "text": text},
            timeout=15,
        )
    except Exception:
        pass


def _post(method, payload):
    try:
        resp = requests.post(f"{API_BASE}/{method}", data=payload, timeout=30)
        return resp.json()
    except Exception as e:
        return {"ok": False, "description": f"Request failed: {e}"}


def _json(obj):
    import json
    return json.dumps(obj)
