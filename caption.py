"""
Galaxy Gamez - Post caption format
"""

from bs4 import BeautifulSoup

from config import WHATSAPP_LINKS, TELEGRAM_LINK, WEBSITE_LINK


def extract_image(entry):
    html = entry.get("summary", "")
    soup = BeautifulSoup(html, "html.parser")
    img = soup.find("img")
    return img["src"] if img and img.get("src") else None


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
