"""
ingestion.py — Global death ingestion from Wikidata.

Queries Wikidata SPARQL for people whose P570 (date of death) falls within a
configurable recent window, then confirms each candidate via the English Wikipedia
article before writing to the deaths table:

  1. Article must NOT be in Category:Living people.
  2. Infobox death_date must pass the same extract_death_date() validation used
     by the watcher — same standards, different source.

Only confirmed deaths are upserted.  Idempotent: re-running for the same window
never creates duplicates (keyed on wiki_qid).

Designed to run ONLY on GitHub Actions (see .github/workflows/ingestor.yml).
Never imported by the Render web app.
"""

import json
import logging
import os
import re
import time
from datetime import UTC, datetime, timedelta

log = logging.getLogger(__name__)

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
WIKI_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {
    "User-Agent": (
        "ObituaryWatch/3.0 (global-death-ingestor; "
        "github.com/MichelHoudini/obituary-watch; brainiackson@gmail.com)"
    )
}

INGESTOR_WINDOW_DAYS: int = int(os.environ.get("INGESTOR_WINDOW_DAYS", "3"))
BATCH_SLEEP_SECONDS: float = float(os.environ.get("INGESTOR_BATCH_SLEEP", "1.0"))

# ── Offline test-mode state ───────────────────────────────────────────────────
# Set by conftest.py (never in production).  When True, network calls are
# replaced by lookups against these dicts.
_OFFLINE_MODE: bool = False
# list[dict] with keys: qid, wiki_title, display_name, death_date_raw, categories, wikitext
_FIXTURE_DEATHS: list[dict] = []

_SPARQL_QUERY = """
SELECT DISTINCT ?person ?personLabel ?deathDate ?article ?wikiTitle WHERE {{
  ?person wdt:P570 ?deathDate.
  FILTER(?deathDate >= "{from_date}"^^xsd:dateTime)
  FILTER(?deathDate <  "{to_date}"^^xsd:dateTime)
  ?article schema:about ?person;
           schema:isPartOf <https://en.wikipedia.org/>;
           schema:name ?wikiTitle.
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT 500
"""

_QID_RE = re.compile(r"Q[0-9]+$")


def _qid_from_uri(uri: str) -> str | None:
    m = _QID_RE.search(uri)
    return m.group(0) if m else None


def query_wikidata_deaths(days_back: int) -> list[dict]:
    """Return raw SPARQL rows for people who died in the last `days_back` days.
    Each row: {qid, wiki_title, display_name, death_date_raw}.
    In offline mode, returns _FIXTURE_DEATHS instead."""
    if _OFFLINE_MODE:
        # Return full fixture dicts so confirm_death() can use categories/wikitext
        return [dict(d) for d in _FIXTURE_DEATHS]

    import requests

    now = datetime.now(UTC)
    from_dt = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
    to_dt = now.strftime("%Y-%m-%dT23:59:59Z")
    sparql = _SPARQL_QUERY.format(from_date=from_dt, to_date=to_dt)

    try:
        r = requests.get(
            WIKIDATA_ENDPOINT,
            params={"query": sparql, "format": "json"},
            headers=HEADERS,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        log.error("Wikidata SPARQL query failed: %s", exc)
        return []

    results = []
    for row in data.get("results", {}).get("bindings", []):
        qid = _qid_from_uri(row.get("person", {}).get("value", ""))
        wiki_title = row.get("wikiTitle", {}).get("value", "").replace(" ", "_")
        label = row.get("personLabel", {}).get("value", wiki_title.replace("_", " "))
        death_date_raw = row.get("deathDate", {}).get("value", "")
        if qid and wiki_title:
            results.append(
                {
                    "qid": qid,
                    "wiki_title": wiki_title,
                    "display_name": label,
                    "death_date_raw": death_date_raw,
                }
            )
    return results


def _fetch_wikipedia_data(wiki_title: str) -> tuple[list[str], str | None]:
    """Return (category_names, wikitext) for a Wikipedia article.
    Returns ([], None) on error."""
    import requests

    try:
        r = requests.get(
            WIKI_API,
            params={
                "action": "query",
                "titles": wiki_title.replace("_", " "),
                "prop": "categories|revisions",
                "cllimit": "50",
                "rvprop": "content",
                "rvslots": "main",
                "formatversion": "2",
                "format": "json",
            },
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", [])
        if not pages:
            return [], None
        page = pages[0]
        cats = [c.get("title", "") for c in page.get("categories", [])]
        wikitext = None
        revs = page.get("revisions", [])
        if revs:
            wikitext = revs[0].get("slots", {}).get("main", {}).get("content")
        return cats, wikitext
    except Exception as exc:
        log.warning("Wikipedia fetch failed for %s: %s", wiki_title, exc)
        return [], None


def confirm_death(candidate: dict) -> tuple[bool, str | None]:
    """Confirm that a death candidate is real via Wikipedia.

    Returns (confirmed, validated_death_date_string).
    confirmed=True only when:
      1. Article is NOT in Category:Living people
      2. extract_death_date() on the wikitext returns a non-None value

    In offline mode, uses fixture data attached to the candidate dict.
    """
    from app.watcher import extract_death_date

    if _OFFLINE_MODE:
        cats = candidate.get("categories", [])
        wikitext = candidate.get("wikitext", "")
    else:
        cats, wikitext = _fetch_wikipedia_data(candidate["wiki_title"])

    if "Category:Living people" in cats:
        log.debug("%s: still in 'Living people' — skip", candidate["wiki_title"])
        return False, None

    if not wikitext:
        log.debug("%s: no wikitext — skip", candidate["wiki_title"])
        return False, None

    death_date = extract_death_date(wikitext)
    if not death_date:
        log.debug("%s: extract_death_date returned None — skip", candidate["wiki_title"])
        return False, None

    return True, death_date


def run(days_back: int | None = None, dry_run: bool = False) -> dict:
    """Ingest confirmed deaths from Wikidata for the last `days_back` days.

    Returns summary: {checked, confirmed, inserted, skipped_existing, errors}.
    dry_run=True logs what would be inserted but writes nothing.
    """
    from app.db import has_death_by_qid, is_already_dead, upsert_global_death
    from app.filters import enrich_death

    if days_back is None:
        days_back = INGESTOR_WINDOW_DAYS

    summary = {"checked": 0, "confirmed": 0, "inserted": 0, "skipped_existing": 0, "errors": 0}

    candidates = query_wikidata_deaths(days_back)
    log.info("Wikidata returned %d candidates (window=%d days)", len(candidates), days_back)

    for cand in candidates:
        summary["checked"] += 1
        qid = cand["qid"]
        wiki_title = cand["wiki_title"]

        try:
            if has_death_by_qid(qid) or is_already_dead(wiki_title):
                summary["skipped_existing"] += 1
                continue

            confirmed, death_date = confirm_death(cand)
            if not confirmed:
                continue

            summary["confirmed"] += 1
            wiki_url = f"https://en.wikipedia.org/wiki/{wiki_title}"

            if dry_run:
                log.info("[DRY-RUN] Would insert: %s (%s) died %s", wiki_title, qid, death_date)
                continue

            is_new = upsert_global_death(
                wiki_qid=qid,
                wiki_title=wiki_title,
                display_name=cand["display_name"],
                death_date=death_date,
                wiki_url=wiki_url,
            )
            if is_new:
                summary["inserted"] += 1
                log.info("Ingested: %s (%s) died %s", wiki_title, qid, death_date)
                enrich_death(wiki_title)

            if not _OFFLINE_MODE:
                time.sleep(BATCH_SLEEP_SECONDS)

        except Exception as exc:
            log.error("Error processing %s (%s): %s", wiki_title, qid, exc)
            summary["errors"] += 1

    log.info(
        "Ingestor complete: checked=%d confirmed=%d inserted=%d "
        "skipped_existing=%d errors=%d dry_run=%s",
        summary["checked"], summary["confirmed"], summary["inserted"],
        summary["skipped_existing"], summary["errors"], dry_run,
    )
    return summary


if __name__ == "__main__":
    import sys
    from app.db import init_db, migrate_schema
    from app.observability import setup_logging, setup_sentry

    setup_logging()
    setup_sentry("ingestor")
    log = logging.getLogger(__name__)

    dry_run = "--dry-run" in sys.argv
    days_arg = next((a for a in sys.argv[1:] if a.isdigit()), None)
    days_back = int(days_arg) if days_arg else INGESTOR_WINDOW_DAYS

    init_db()
    migrate_schema()
    result = run(days_back=days_back, dry_run=dry_run)
    log.info("Summary: %s", json.dumps(result))
