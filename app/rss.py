"""
rss.py - Build Atom/RSS feed from detected deaths.
"""

from datetime import datetime, timezone
from feedgen.feed import FeedGenerator
from app.db import get_deaths


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
        death_info = f"Death date: {row['death_date']}" if row.get("death_date") else "Date not yet confirmed"
        fe.content(f"<p><strong>{row['display_name']}</strong> has died. {death_info}</p><p><a href=\"{row['wiki_url']}\">Wikipedia</a></p>", type="html")
        fe.summary(f"{row['display_name']} has died. {death_info}")
        try:
            dt = datetime.fromisoformat(row["detected_at"]).replace(tzinfo=timezone.utc)
        except Exception:
            dt = datetime.now(timezone.utc)
        fe.published(dt)
        fe.updated(dt)

    return fg.atom_str(pretty=True)