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

POSTS_PER_CYCLE_OPTIONS = [1, 2, 3, 5]
DEFAULT_POSTS_PER_CYCLE = 3  # Josh's own channels

POST_NOW_COOLDOWN_SECONDS = 60  # prevents rapid-tap spam from blocking the whole bot

# ---------------- GEMZ COST FORMULA (used once Step 2 currency is built) ----------------
GEMZ_COST_PER_POST = 1          # deducted every time a post actually sends
GEMZ_COST_PER_CHANNEL_PER_DAY = 2  # flat daily upkeep per active connected channel

# ---------------- CUSTOM CAPTION TEMPLATES ----------------
# Josh's own channels always use the fixed GAME NAME format in caption.py.
# Everyone else gets this neutral default unless they set their own -
# available placeholders: {title} and {link}
DEFAULT_GENERIC_TEMPLATE = (
    "📰 {title}\n\n"
    "🔗 {link}\n\n"
    "Powered by Galaxy Gamez Post Assistant"
)

# ---------------- CHANNEL LIMITS ----------------
MAX_CHANNELS_FREE = 2    # non-admin users, free tier
MAX_CHANNELS_PAID = 4    # non-admin hard cap even after paying for more slots
# Admin (Josh) has no limit.

# ---------------- PAYMENTS ----------------
PAYMENT_INFO = {
    "bank_name": "OPay",
    "account_number": "9071662919",
    "account_name": "Josh Ehimika-Irhiemi",
}

# Floor prices - any package labelled "monthly"/"yearly" must be priced at
# or above these, regardless of how many Gemz it contains. A Naira amount
# is NOT 1:1 with a Gemz amount - Josh sets the actual exchange himself.
MIN_MONTHLY_PRICE_NAIRA = 5000
MIN_YEARLY_PRICE_NAIRA = 10000

# Exchange rate: how many Naira buys 1 Gemz. Change this single number to
# reprice everything below - Naira and Gemz are deliberately NOT 1:1.
NAIRA_PER_GEMZ = 5

# Gemz floor is calculated, not guessed: cheapest possible real usage is
# 1 channel, posting once every 7 days, 1 post per cycle -
#   (1 channel * GEMZ_COST_PER_CHANNEL_PER_DAY) + (1 post / 7 days * GEMZ_COST_PER_POST)
#   = 2 + 0.143 =~ 2.14 Gemz/day
# A full month of even that lightest possible usage is only ~65 Gemz, but
# Josh set a hard floor of 1000 Gemz for the smallest sellable monthly
# package regardless - that floor dominates and is used directly below.
MIN_MONTHLY_GEMZ = 1000
MIN_YEARLY_GEMZ = MIN_MONTHLY_GEMZ * 10  # yearly priced like "10 months for 12" - a real discount vs paying monthly x12

# Real packages, priced at the exchange rate above, always at/above the
# Naira floors. Edit gemz/price_naira here any time - NAIRA_PER_GEMZ stays
# the single source of truth for the conversion.
GEMZ_PACKAGES = [
    {"label": "Monthly Starter", "gemz": MIN_MONTHLY_GEMZ, "price_naira": max(MIN_MONTHLY_GEMZ * NAIRA_PER_GEMZ, MIN_MONTHLY_PRICE_NAIRA), "period": "monthly"},
    {"label": "Monthly Plus", "gemz": MIN_MONTHLY_GEMZ * 2, "price_naira": (MIN_MONTHLY_GEMZ * 2) * NAIRA_PER_GEMZ, "period": "monthly"},
    {"label": "Monthly Pro", "gemz": MIN_MONTHLY_GEMZ * 5, "price_naira": (MIN_MONTHLY_GEMZ * 5) * NAIRA_PER_GEMZ, "period": "monthly"},
    {"label": "Monthly Max", "gemz": MIN_MONTHLY_GEMZ * 10, "price_naira": (MIN_MONTHLY_GEMZ * 10) * NAIRA_PER_GEMZ, "period": "monthly"},
    {"label": "Yearly Starter", "gemz": MIN_YEARLY_GEMZ, "price_naira": max(MIN_YEARLY_GEMZ * NAIRA_PER_GEMZ, MIN_YEARLY_PRICE_NAIRA), "period": "yearly"},
    {"label": "Yearly Plus", "gemz": MIN_YEARLY_GEMZ * 2, "price_naira": (MIN_YEARLY_GEMZ * 2) * NAIRA_PER_GEMZ, "period": "yearly"},
    {"label": "Yearly Pro", "gemz": MIN_YEARLY_GEMZ * 5, "price_naira": (MIN_YEARLY_GEMZ * 5) * NAIRA_PER_GEMZ, "period": "yearly"},
    {"label": "Yearly Max", "gemz": MIN_YEARLY_GEMZ * 10, "price_naira": (MIN_YEARLY_GEMZ * 10) * NAIRA_PER_GEMZ, "period": "yearly"},
]

# ---------------- REFERRALS ----------------
REFERRAL_REWARD_GEMZ = 200  # both referrer and new user get this once the referral completes
BOT_USERNAME = "VyroAgentRo_bot"  # used to build referral links - update if the bot's @username changes
BROADCAST_GRACE_HOURS = 4    # user has this long before deleting a broadcast counts against them
STRIKE_LIMIT = 3             # 3rd strike = permanent ban

# ---------------- FILES (all committed back to repo by GitHub Actions) ----------------
USERS_FILE = "users.json"
BROADCASTS_FILE = "broadcasts.json"
STATE_FILE = "state.json"
STATS_FILE = "stats.json"
LOG_FILE = "last_run_log.txt"
