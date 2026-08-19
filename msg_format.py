"""
Galaxy Gamez - Message Formatting Helper
Converts a Telegram message's text/caption + entities into HTML, so we can
prepend a native <blockquote> "ADVERTISEMENT" label and send it all as ONE
message (preserving the original bold/italic/links) instead of two separate
message bubbles.
"""

TAG_MAP = {
    "bold": ("<b>", "</b>"),
    "italic": ("<i>", "</i>"),
    "underline": ("<u>", "</u>"),
    "strikethrough": ("<s>", "</s>"),
    "code": ("<code>", "</code>"),
    "pre": ("<pre>", "</pre>"),
    "spoiler": ("<tg-spoiler>", "</tg-spoiler>"),
}


def _escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def entities_to_html(text, entities):
    """Telegram entity offsets/lengths are in UTF-16 code units, so we work
    on a UTF-16 buffer to slice correctly even with emoji/non-BMP chars."""
    if not text:
        return ""
    if not entities:
        return _escape(text)

    utf16 = text.encode("utf-16-le")

    # Collect open/close events per UTF-16 offset
    events = {}  # offset -> {"opens": [tag,...], "closes": [tag,...]}

    def add_event(offset, key, tag):
        events.setdefault(offset, {"opens": [], "closes": []})[key].append(tag)

    for e in entities:
        etype = e.get("type")
        start = e["offset"]
        end = start + e["length"]

        if etype in TAG_MAP:
            open_tag, close_tag = TAG_MAP[etype]
        elif etype == "text_link" and e.get("url"):
            open_tag = f'<a href="{_escape(e["url"])}">'
            close_tag = "</a>"
        else:
            continue  # unsupported entity type (mention, hashtag, etc.) - leave as plain text

        add_event(start, "opens", open_tag)
        add_event(end, "closes", close_tag)

    offsets = sorted(events.keys())
    out = []
    last = 0
    for off in offsets:
        chunk = utf16[last * 2: off * 2].decode("utf-16-le", errors="ignore")
        out.append(_escape(chunk))
        # closes before opens at the same position
        for tag in reversed(events[off]["closes"]):
            out.append(tag)
        for tag in events[off]["opens"]:
            out.append(tag)
        last = off

    tail = utf16[last * 2:].decode("utf-16-le", errors="ignore")
    out.append(_escape(tail))
    return "".join(out)


def extract_message_content(message):
    """Returns a plain-dict snapshot of a message's content that's safe to
    store in JSON (for recurring broadcasts) and reuse later - Telegram's
    Bot API has no 'get message by id' endpoint, so this must be captured
    up front rather than re-fetched each time."""
    if message.get("photo"):
        photo_file_id = message["photo"][-1]["file_id"]  # largest size is last
        return {
            "kind": "photo",
            "photo_file_id": photo_file_id,
            "text": message.get("caption", ""),
            "entities": message.get("caption_entities", []),
        }
    return {
        "kind": "text",
        "photo_file_id": None,
        "text": message.get("text", ""),
        "entities": message.get("entities", []),
    }


def build_ad_html(content):
    """Builds the final HTML: a native quote-block ad label at the top,
    followed by the original content with formatting preserved."""
    label = "<blockquote>📢 ADVERTISEMENT</blockquote>"
    body = entities_to_html(content["text"], content["entities"])
    return f"{label}\n{body}" if body else label
