"""
Galaxy Gamez - Gemz Usage Estimator
Instead of listing every possible combination of schedule x posts-per-cycle
x channel-count as a static table (144+ rows, unreadable on mobile), this
powers an interactive 3-question calculator: pick channels, pick schedule,
pick posts-per-cycle, get a real number back.
"""

from config import GEMZ_COST_PER_POST, GEMZ_COST_PER_CHANNEL_PER_DAY


def daily_cost_per_channel(interval_hours, posts_per_cycle):
    posts_per_day = posts_per_cycle * (24 / interval_hours)
    return posts_per_day * GEMZ_COST_PER_POST + GEMZ_COST_PER_CHANNEL_PER_DAY


def estimate_days(gemz_amount, channels, interval_hours, posts_per_cycle):
    total_daily_cost = daily_cost_per_channel(interval_hours, posts_per_cycle) * channels
    if total_daily_cost <= 0:
        return None
    return gemz_amount / total_daily_cost


def format_duration(days):
    if days is None:
        return "N/A"
    if days >= 30:
        return f"{days / 30:.1f} month(s) ({days:.0f} days)"
    if days >= 7:
        return f"{days / 7:.1f} week(s) ({days:.0f} days)"
    return f"{days:.1f} day(s)"
