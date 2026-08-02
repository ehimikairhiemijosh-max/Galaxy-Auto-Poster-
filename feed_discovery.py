"""
Galaxy Gamez - Feed Discovery
Given a plain website URL (not a feed link), finds the actual RSS/Atom feed
automatically. Supports WordPress, Blogger, Medium, Ghost, and any standard
RSS-enabled site - users never need to know their own feed URL.
"""

import requests
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import urljoin

COMMON_FEED_PATHS = [
    "/feed/",           # WordPress
    "/feed",
    "/rss/",            # Ghost
    "/rss",
    "/feeds/posts/default",  # Blogger
    "/atom.xml",
    "/rss.xml",
    "/index.xml",
]


def _looks_like_valid_feed(url):
    try:
        parsed = feedparser.parse(url)
    except Exception:
        return False
    return len(parsed.entries) > 0


def _find_feed_in_html(site_url):
    """Standard method: every real blogging platform declares its feed via
    a <link rel="alternate" type="application/rss+xml"> tag in <head>."""
    try:
        resp = requests.get(site_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return None

    for link in soup.find_all("link", rel="alternate"):
        type_attr = (link.get("type") or "").lower()
        if "rss" in type_attr or "atom" in type_attr or "xml" in type_attr:
            href = link.get("href")
            if href:
                return urljoin(site_url, href)
    return None


def discover_feed(user_input):
    """Takes whatever the user typed (a site URL or already a feed URL) and
    returns a working feed URL, or None if nothing could be found."""
    user_input = user_input.strip()
    if not user_input.startswith("http"):
        user_input = "https://" + user_input

    # 1. Maybe they already pasted a direct, working feed URL
    if _looks_like_valid_feed(user_input):
        return user_input

    # 2. Look for the feed declared in the site's own HTML (most reliable)
    found = _find_feed_in_html(user_input)
    if found and _looks_like_valid_feed(found):
        return found

    # 3. Fall back to trying common platform feed paths
    base = user_input.rstrip("/")
    for path in COMMON_FEED_PATHS:
        candidate = base + path
        if _looks_like_valid_feed(candidate):
            return candidate

    return None
