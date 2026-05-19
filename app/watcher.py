"""
watcher.py — Wikipedia RecentChanges stream listener.
Monitors edits to watched articles and detects death_date additions.
Sends email notification to all subscribers when death is detected.
"""

import json
import logging
import time
import re
import requests
import sseclient
import mwparserfromhell

from app.db import get_all_watched_titles, record_death, is_already_dead, get_emails_for
from app.email import send_death_notification

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

STREAM_URL = "https://stream.wikimedia.org/v2/stream/recentchange"
WIKI_API   = "https://en.wikipedia.org/w/api.php"
HEADERS    = {"User-Agent": "ObituaryWatch/3.0 (wikipedia-death-monitor)"}
REFRESH_EVERY = 200


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


def extract_death_date(wikitext: str) -> str | None:
    try:
        parsed = mwparserfromhell.parse(wikitext)
        for t in parsed.filter_templates():
            if "infobox" not in t.name.strip().lower():
                continue
            if t.has("death_date"):
                val = str(t.get("death_date").value).strip()
                if val:
                    return val
    except Exception:
        pass
    return None


def send_death_notification(wiki_title: str, display_name: str, death_date: str, edit_url: str):
    """
    Send email notification to all watchers.
    Email service to be implemented — for now logs to console.
    Replace this function body with actual email sending (Gmail SMTP, SendGrid, etc.)
    """
    emails = get_emails_for(wiki_title)
    if not emails:
        log.info(f"No watchers for {display_name}")
        return

    log.info(f"SENDING NOTIFICATIONS: {display_name} died. Emailing {len(emails)} subscriber(s): {emails}")

    # TODO: implement email sending here
    # Example with Gmail SMTP:
    # import smtplib
    # from email.message import EmailMessage
    # msg = EmailMessage()
    # msg["Subject"] = f"ObituaryWatch: {display_name} has died"
    # msg["From"] = "noreply@obituarywatch.com"
    # msg.set_content(f"{display_name} has died.\n\nWikipedia: https://en.wikipedia.org/wiki/{wiki_title}")
    # with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
    #     smtp.login(EMAIL_USER, EMAIL_PASS)
    #     for email in emails:
    #         msg["To"] = email
    #         smtp.send_message(msg)


def run():
    log.info("Starting ObituaryWatch watcher")
    watched  = get_all_watched_titles()
    log.info(f"Watching {len(watched)} articles")
    count   = 0
    backoff = 5

    while True:
        try:
            log.info("Connecting to Wikipedia RecentChanges stream...")
            r = requests.get(STREAM_URL, stream=True, headers=HEADERS, timeout=60)
            client  = sseclient.SSEClient(r)
            backoff = 5

            for event in client.events():
                if not event.data:
                    continue
                try:
                    data = json.loads(event.data)
                except Exception:
                    continue

                if data.get("wiki") != "enwiki":         continue
                if data.get("namespace") != 0:           continue
                if data.get("type") not in ("edit","new"): continue

                title = data.get("title", "").replace(" ", "_")
                if title not in watched:                  continue
                if is_already_dead(title):                continue

                log.info(f"Watched article edited: {title}")
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
                    for email in emails:
                        send_death_notification(
                            to_email=email,
                            person_name=display_name,
                            wiki_title=title,
                            death_date=death_date,
                            wiki_url=wiki_url,
                            edit_url=edit_url,
                        )
                    log.info(f"Notified {len(emails)} subscriber(s)")

                count += 1
                if count % REFRESH_EVERY == 0:
                    watched = get_all_watched_titles()
                    log.info(f"Refreshed: watching {len(watched)} articles")

        except Exception as e:
            log.error(f"Stream error: {e}. Reconnecting in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)


if __name__ == "__main__":
    from app.db import init_db
    init_db()
    run()
