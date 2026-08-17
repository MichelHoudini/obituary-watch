"""
rss.py - Build Atom/RSS feed from detected deaths.
"""

import re
from datetime import UTC, datetime

from feedgen.feed import FeedGenerator

from app.db import get_deaths

_MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"]


def _format_death_date(raw: str | None) -> str:
    """Same logic as app.main.format_death_date, duplicated here (small,
    pure function) to avoid a cross-module import for one helper."""
    if not raw:
        return "confirmed"
    match = re.search(
        r"\{\{\s*[Dd]eath date(?: and age)?\s*\|\s*(\d{4})\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})",
        raw,
    )
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if 1 <= month <= 12:
            return f"{_MONTH_NAMES[month]} {day}, {year}"
    return raw


def build_global_feed(base_url: str) -> bytes:
    feed_url = f"{base_url}/rss"
    fg = FeedGenerator()
    fg.id(feed_url)
    fg.title("Mortivox - Death Alerts")
    fg.subtitle("Wikipedia-detected deaths of notable people")
    fg.link(href=base_url, rel="alternate")
    fg.link(href=feed_url, rel="self")
    fg.language("en")
    fg.author({"name": "Mortivox", "email": "noreply@mortivox.com"})

    for row in get_deaths(limit=100):
        fe = fg.add_entry()
        fe.id(row["wiki_url"])
        fe.title(f"{row['display_name']} has died")
        fe.link(href=row["wiki_url"])
        death_info = f"Death date: {_format_death_date(row.get('death_date'))}" if row.get("death_date") else "Date not yet confirmed"
        fe.content(f"<p><strong>{row['display_name']}</strong> has died. {death_info}</p><p><a href=\"{row['wiki_url']}\">Wikipedia</a></p>", type="html")
        fe.summary(f"{row['display_name']} has died. {death_info}")
        try:
            dt = datetime.fromisoformat(row["detected_at"]).replace(tzinfo=UTC)
        except Exception:
            dt = datetime.now(UTC)
        fe.published(dt)
        fe.updated(dt)

    return fg.atom_str(pretty=True)