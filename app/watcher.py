"""
watcher.py — Wikipedia RecentChanges stream listener.
Monitors edits to watched articles and detects death_date additions.
Sends email notification to all subscribers when death is detected.
"""

import json
import logging
import re
import time

import mwparserfromhell
import requests
import sseclient

from app.db import (
    get_all_watched_titles,
    get_emails_for,
    is_already_dead,
    record_death,
    record_watcher_error,
    record_watcher_event,
    record_watcher_heartbeat,
    record_watcher_start,
)
from app.email import send_death_notification as send_death_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

STREAM_URL = "https://stream.wikimedia.org/v2/stream/recentchange"
WIKI_API   = "https://en.wikipedia.org/w/api.php"
HEADERS    = {"User-Agent": "ObituaryWatch/3.0 (wikipedia-death-monitor)"}
REFRESH_EVERY = 200
HEARTBEAT_INTERVAL = 60  # seconds between DB heartbeat writes (avoid writing on every stream event)


def fetch_wikitext(title: str) -> str | None:
    try:
        r = requests.get(WIKI_API, params={
            "action": "query", "prop": "revisions", "titles": title,
            "rvprop": "content", "rvslots": "main",
            "formatversion": "2", "format": "json",
        }, headers=HEADERS, timeout=10)
        return r.json()["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
    except Exception as e:
        log.warning(f"Failed to fetch wikitext for {title}: {e}")
        return None


# Wikipedia's Person infobox template commonly ships with this exact
# boilerplate comment in the death_date field as an editor hint, even on
# articles about people who are alive:
#   <!-- {{Death date and age|YYYY|MM|DD|YYYY|MM|DD}} (DEATH date then BIRTH date) -->
# A naive "field is non-empty" check treats this as a real death date. This
# caused a false positive on Clint Eastwood (still alive) on 2026-07-26: the
# triggering edit was an unrelated Filmography change, and the death_date
# field had carried this exact placeholder the whole time.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def extract_death_date(wikitext: str) -> str | None:
    try:
        parsed = mwparserfromhell.parse(wikitext)
        for t in parsed.filter_templates():
            if "infobox" not in t.name.strip().lower():
                continue
            if t.has("death_date"):
                val = str(t.get("death_date").value).strip()
                if not val:
                    continue
                # Strip HTML comments before validating. If the value is
                # nothing but a comment (the placeholder case above), or has
                # no real date data (a genuine date always has a 4-digit
                # year), it isn't an actual death date.
                real_content = _HTML_COMMENT_RE.sub("", val).strip()
                if not real_content or not re.search(r"\d{4}", real_content):
                    continue
                return val
    except Exception:
        pass
    return None


def run():
    log.info("Starting ObituaryWatch watcher")
    record_watcher_start()
    watched  = get_all_watched_titles()
    log.info(f"Watching {len(watched)} articles")
    count   = 0
    backoff = 5
    last_heartbeat_ts = 0.0

    while True:
        try:
            log.info("Connecting to Wikipedia RecentChanges stream...")
            r = requests.get(STREAM_URL, stream=True, headers=HEADERS, timeout=60)
            client  = sseclient.SSEClient(r)
            backoff = 5

            for event in client.events():
                now_ts = time.time()
                if now_ts - last_heartbeat_ts >= HEARTBEAT_INTERVAL:
                    record_watcher_heartbeat()
                    last_heartbeat_ts = now_ts

                if not event.data:
                    continue
                try:
                    data = json.loads(event.data)
                except Exception:
                    continue

                if data.get("wiki") != "enwiki":
                    continue
                if data.get("namespace") != 0:
                    continue
                if data.get("type") not in ("edit", "new"):
                    continue

                title = data.get("title", "").replace(" ", "_")
                if title not in watched:
                    continue
                if is_already_dead(title):
                    continue

                log.info(f"Watched article edited: {title}")
                record_watcher_event(title)
                wikitext = fetch_wikitext(title)
                if not wikitext or "death_date" not in wikitext:
                    continue

                death_date = extract_death_date(wikitext)
                if not death_date:
                    continue

                rev_id   = data.get("revision", {}).get("new")
                edit_url = f"https://en.wikipedia.org/w/index.php?diff={rev_id}" if rev_id else None

                display_name = title.replace("_", " ")
                is_new = record_death(title, display_name, death_date, edit_url)
                if is_new:
                    log.info(f"DEATH DETECTED: {display_name} — {death_date}")
                    emails = get_emails_for(title)
                    wiki_url = f"https://en.wikipedia.org/wiki/{title}"
                    sent = 0
                    for email in emails:
                        if send_death_email(
                            to_email=email,
                            person_name=display_name,
                            wiki_title=title,
                            death_date=death_date,
                            wiki_url=wiki_url,
                            edit_url=edit_url,
                        ):
                            sent += 1
                    log.info(f"Notified {sent}/{len(emails)} subscriber(s)")

                count += 1
                if count % REFRESH_EVERY == 0:
                    watched = get_all_watched_titles()
                    log.info(f"Refreshed: watching {len(watched)} articles")

        except Exception as e:
            log.error(f"Stream error: {e}. Reconnecting in {backoff}s")
            record_watcher_error(e)
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)


if __name__ == "__main__":
    from app.db import init_db
    init_db()
    run()
