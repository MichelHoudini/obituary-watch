"""
rss.py — Build Atom/RSS feeds from detected deaths.

Users subscribe to these feeds in any RSS reader (Feedly, NewsBlur,
NetNewsWire, etc.) — completely free, no email infrastructure needed.
"""

from datetime import datetime, timezone
from feedgen.feed import FeedGenerator
from app.db import get_deaths, get_list_deaths


def _make_feed(title: str, description: str, base_url: str, feed_url: str) -> FeedGenerator:
    fg = FeedGenerator()
    fg.id(feed_url)
    fg.title(title)
    fg.subtitle(description)
    fg.link(href=base_url, rel="alternate")
    fg.link(href=feed_url, rel="self")
    fg.language("en")
    fg.author({"name": "ObituaryWatch", "email": "noreply@obituarywatch.local"})
    return fg


def _add_entry(fg: FeedGenerator, row: dict):
    fe = fg.add_entry()
    fe.id(row["wiki_url"])
    fe.title(f"{row['display_name']} has died")
    fe.link(href=row["wiki_url"])

    death_info = f"Death date: {row['death_date']}" if row["death_date"] else "Date not yet confirmed"
    body = f"""
    <p><strong>{row['display_name']}</strong> has died.</p>
    <p>{death_info}</p>
    <p>
      <a href="{row['wiki_url']}">Wikipedia article</a>
      {f' | <a href="{row["edit_url"]}">See edit that detected this</a>' if row.get("edit_url") else ""}
    </p>
    <p><small>Detected by ObituaryWatch at {row['detected_at']} UTC</small></p>
    """
    fe.content(body.strip(), type="html")
    fe.summary(f"{row['display_name']} has died. {death_info}")

    try:
        dt = datetime.fromisoformat(row["detected_at"]).replace(tzinfo=timezone.utc)
    except Exception:
        dt = datetime.now(timezone.utc)
    fe.published(dt)
    fe.updated(dt)


def build_global_feed(base_url: str) -> bytes:
    """Atom feed of all detected deaths."""
    feed_url = f"{base_url}/rss"
    fg = _make_feed(
        title="ObituaryWatch — All Deaths",
        description="Wikipedia-detected deaths of notable people",
        base_url=base_url,
        feed_url=feed_url,
    )
    for row in get_deaths(limit=100):
        _add_entry(fg, dict(row))
    return fg.atom_str(pretty=True)


def build_list_feed(list_slug: str, base_url: str) -> bytes | None:
    """Atom feed scoped to a named watchlist."""
    rows = get_list_deaths(list_slug)
    if rows is None:
        return None
    feed_url = f"{base_url}/rss/{list_slug}"
    fg = _make_feed(
        title=f"ObituaryWatch — {list_slug}",
        description=f"Deaths detected for watchlist: {list_slug}",
        base_url=base_url,
        feed_url=feed_url,
    )
    for row in rows:
        _add_entry(fg, dict(row))
    return fg.atom_str(pretty=True)
