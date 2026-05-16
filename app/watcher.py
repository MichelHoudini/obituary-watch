import json
import logging
import time
import requests
import sseclient
import mwparserfromhell

from app.db import (
    get_watched_titles, record_death,
    is_already_dead, mark_checked,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

STREAM_URL = "https://stream.wikimedia.org/v2/stream/recentchange"
WIKI_API   = "https://en.wikipedia.org/w/api.php"
HEADERS    = {"User-Agent": "ObituaryWatch/1.0 (your@email.com)"}
REFRESH_EVERY = 500


def fetch_wikitext(title):
    params = {"action":"query","prop":"revisions","titles":title,
              "rvprop":"content","rvslots":"main","formatversion":"2","format":"json"}
    try:
        r = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=10)
        return r.json()["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
    except Exception as e:
        log.warning(f"Failed to fetch {title}: {e}")
        return None


def extract_death_date(wikitext):
    parsed = mwparserfromhell.parse(wikitext)
    for t in parsed.filter_templates():
        name = t.name.strip().lower()
        if "infobox" not in name:
            continue
        if t.has("death_date"):
            val = str(t.get("death_date").value).strip()
            if val:
                return val
    return None


def run():
    log.info("Starting ObituaryWatch Wikipedia stream listener")
    watched = get_watched_titles()
    log.info(f"Loaded {len(watched)} watched titles")
    event_count = 0
    backoff = 5

    while True:
        try:
            log.info(f"Connecting to RecentChanges stream...")
            r = requests.get(STREAM_URL, stream=True, headers=HEADERS, timeout=60)
            client = sseclient.SSEClient(r)
            backoff = 5

            for event in client.events():
                if not event.data:
                    continue
                try:
                    data = json.loads(event.data)
                except:
                    continue

                if data.get("wiki") != "enwiki": continue
                if data.get("namespace") != 0: continue
                if data.get("type") not in ("edit","new"): continue

                title = data.get("title","").replace(" ","_")
                if title not in watched: continue
                if is_already_dead(title): continue

                log.info(f"Watched article edited: {title}")
                mark_checked(title)
                wikitext = fetch_wikitext(title)
                if not wikitext or "death_date" not in wikitext: continue

                death_date = extract_death_date(wikitext)
                if not death_date: continue

                rev_id = data.get("revision",{}).get("new")
                edit_url = f"https://en.wikipedia.org/w/index.php?diff={rev_id}" if rev_id else None
                if record_death(title, title.replace("_"," "), death_date, edit_url):
                    log.info(f"DEATH DETECTED: {title} — {death_date}")

                event_count += 1
                if event_count % REFRESH_EVERY == 0:
                    watched = get_watched_titles()

        except Exception as e:
            log.error(f"Error: {e}. Reconnecting in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)


if __name__ == "__main__":
    from app.db import init_db
    init_db()
    run()