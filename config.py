"""
Galaxy Gamez - Central Settings
"""

import os

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")

# ---------------- JOSH'S OWN CHANNELS (default/admin account) ----------------
DEFAULT_CHANNEL_IDS = [
    -1002328517911,  # main channel
    -1001959406158,
    -1002392805703,
    -1002685110307,
    -1002353908594,
    -1002721819829,
]
DEFAULT_BLOG_FEED_URL = "https://galaxygamez01.blogspot.com/feeds/posts/default?max-results=500"

# ---------------- BRANDING (stays fixed on every post, regardless of whose channel) ----------------
WHATSAPP_LINKS = [
    "https://whatsapp.com/channel/0029Vb46RraF6smzVwGhZL2H",
    "https://whatsapp.com/channel/0029Vb56sG2IHphDA7uhWJ3C",
]
TELEGRAM_LINK = "https://t.me/GALAXYGAMEZ01"
WEBSITE_LINK = "https://galaxygamez01.blogspot.com"
SUPPORT_HANDLE = "@galaxygamezsupport"

# ---------------- FORCE-JOIN GATE ----------------
# Public @usernames the bot checks membership against before answering ANY command.
FORCE_JOIN_CHATS = [
    {"username": "GALAXYGAMEZ01", "label": "📢 Channel 1", "url": "https://t.me/GALAXYGAMEZ01"},
    {"username": "galaxygamez02", "label": "📢 Channel 2", "url": "https://t.me/galaxygamez02"},
    {"username": "GALAXYGAMEZCHAT", "label": "💬 Group 1", "url": "https://t.me/GALAXYGAMEZCHAT"},
    {"username": "galaxygamezchat2", "label": "💬 Group 2", "url": "https://t.me/galaxygamezchat2"},
]

# ---------------- POSTING BEHAVIOUR ----------------
POSTS_PER_CYCLE = 3          # 3 unique, sequential posts per channel per cycle
DELAY_BETWEEN_CHANNELS = 2   # seconds
RETRY_ATTEMPTS = 5

# ---------------- PER-CHANNEL SCHEDULING ----------------
# Users pick their own posting frequency when adding a channel.
SCHEDULE_HOUR_OPTIONS = [1, 3, 6, 12, 24]
SCHEDULE_DAY_OPTIONS = [2, 3, 5, 7]
DEFAULT_INTERVAL_HOURS = 3  # Josh's own channels

# ---------------- BROADCAST / STRIKE SYSTEM ----------------
BROADCAST_GRACE_HOURS = 4    # user has this long before deleting a broadcast counts against them
STRIKE_LIMIT = 3             # 3rd strike = permanent ban

# ---------------- FILES (all committed back to repo by GitHub Actions) ----------------
USERS_FILE = "users.json"
BROADCASTS_FILE = "broadcasts.json"
STATE_FILE = "state.json"
STATS_FILE = "stats.json"
LOG_FILE = "last_run_log.txt"
