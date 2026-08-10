"""
Galaxy Gamez - Post caption format
"""

import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from config import WHATSAPP_LINKS, TELEGRAM_LINK, WEBSITE_LINK

_WP_THUMB_SUFFIX = re.compile(r"-\d+x\d+(\.\w+)$")


def extract_image(entry):
    # 1. media:content - genuinely full-size images some platforms (mainly
    #    WordPress) expose separately in feed metadata. Deliberately does
    #    NOT check media:thumbnail here - that field (notably on Blogger)
    #    is often a tiny preview, smaller than the image already embedded
    #    in the post body, so trusting it made image quality WORSE.
    media = entry.get("media_content")
    if media:
        candidates = [m.get("url") for m in media if m.get("url")]
        if candidates:
            candidates.sort(key=lambda u: next(
                (int(m.get("width", 0)) for m in media if m.get("url") == u), 0
            ), reverse=True)
            resolved = urljoin(entry.get("link", ""), candidates[0])
            parsed = urlparse(resolved)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                return resolved

    # 2. Enclosures (RSS <enclosure> tag) - another common place for the
    #    full-size original image
    for link in entry.get("links", []):
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image/"):
            resolved = urljoin(entry.get("link", ""), link.get("href", ""))
            parsed = urlparse(resolved)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                return resolved

    # 3. The image actually embedded in the post body - this is what
    #    always worked before, kept as the primary real-world source.
    html = entry.get("summary", "")
    soup = BeautifulSoup(html, "html.parser")
    img = soup.find("img")
    if not img or not img.get("src"):
        return None

    src = img["src"].strip()
    base = entry.get("link", "")
    resolved = urljoin(base, src)
    parsed = urlparse(resolved)
    if not (parsed.scheme in ("http", "https") and parsed.netloc):
        return None  # not a valid absolute URL - caller falls back to text-only post

    # If it looks like a WordPress-generated thumbnail size (image-300x200.jpg),
    # try the original full-size filename - no network call, so this can
    # never hang or block; if the guess is wrong, Telegram just fails that
    # one send and it's skipped, same as any other bad image URL.
    guess = _WP_THUMB_SUFFIX.sub(r"\1", resolved)
    return guess if guess != resolved else resolved


def build_caption(entry):
    title = entry.title
    return (
        f"❏ 𝐆𝐀𝐌𝐄 𝐍𝐀𝐌𝐄: {title.upper()}\n\n"
        f"╭➤ 𝐃𝐎𝐖𝐍𝐋𝐎𝐀𝐃 👇👇\n"
        f"│ {entry.link}\n"
        f"│\n"
        f"├➤ 𝐏𝐀𝐒𝐒𝐖𝐎𝐑𝐃: 𝐍𝐎𝐍𝐄\n"
        f"│\n"
        f"├➤ 𝐌𝐎𝐑𝐄 𝐆𝐀𝐌𝐄𝐒 👇\n"
        f"│               {WEBSITE_LINK}\n"
        f"│\n"
        f"├➤ 𝐉𝐎𝐈𝐍 𝐓𝐄𝐋𝐄𝐆𝐑𝐀𝐌\n"
        f"│ {TELEGRAM_LINK}\n"
        f"│\n"
        f"├➤ 𝐉𝐎𝐈𝐍 𝐖𝐇𝐀𝐓𝐒𝐀𝐏𝐏 𝟏\n"
        f"│ {WHATSAPP_LINKS[0]}\n"
        f"│\n"
        f"╰➤ 𝐉𝐎𝐈𝐍 𝐖𝐇𝐀𝐓𝐒𝐀𝐏𝐏 𝟐\n"
        f"   {WHATSAPP_LINKS[1]}\n\n"
        f"┏━━━━━━━━━━━━━━━┓\n"
        f"   𝐏𝐎𝐖𝐄𝐑𝐄𝐃 𝐁𝐘: 𝙂𝘼𝙇𝘼𝙓𝙔 𝙂𝘼𝙈𝙀𝙕\n"
        f"┗━━━━━━━━━━━━━━━┛"
    )


def render_caption(entry, template):
    """For every non-admin channel - fills a user-supplied or default
    template. Only {title} and {link} are supported placeholders, kept
    intentionally simple so it can't crash on a malformed custom template."""
    try:
        return template.format(title=entry.title, link=entry.link)
    except (KeyError, IndexError):
        # User's custom template had a typo/bad placeholder - fall back
        # rather than crash the whole posting cycle for that channel.
        return f"{entry.title}\n\n{entry.link}"
