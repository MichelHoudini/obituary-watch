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
MAX_WIKIPEDIA_CALLS: int = int(os.environ.get("INGESTOR_MAX_WIKIPEDIA_CALLS", "100"))
MAX_INSERTS_PER_RUN: int = int(os.environ.get("INGESTOR_MAX_INSERTS", "500"))
SPARQL_TIMEOUT: int = int(os.environ.get("INGESTOR_SPARQL_TIMEOUT", "30"))
SPARQL_MAX_RETRIES: int = 3

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
    In offline mode, returns _FIXTURE_DEATHS instead.
    Retries up to SPARQL_MAX_RETRIES times with exponential backoff on failure."""
    if _OFFLINE_MODE:
        # Return full fixture dicts so confirm_death() can use categories/wikitext
        return [dict(d) for d in _FIXTURE_DEATHS]

    import requests

    now = datetime.now(UTC)
    from_dt = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
    to_dt = now.strftime("%Y-%m-%dT23:59:59Z")
    sparql = _SPARQL_QUERY.format(from_date=from_dt, to_date=to_dt)

    last_exc: Exception | None = None
    for attempt in range(SPARQL_MAX_RETRIES):
        try:
            r = requests.get(
                WIKIDATA_ENDPOINT,
                params={"query": sparql, "format": "json"},
                headers=HEADERS,
                timeout=SPARQL_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            break
        except Exception as exc:
            last_exc = exc
            wait = 2 ** attempt  # 1s, 2s, 4s
            log.warning(
                "Wikidata SPARQL attempt %d/%d failed (%s); retrying in %ds",
                attempt + 1, SPARQL_MAX_RETRIES, exc, wait,
            )
            if attempt < SPARQL_MAX_RETRIES - 1:
                time.sleep(wait)
    else:
        log.error("Wikidata SPARQL query failed after %d attempts: %s", SPARQL_MAX_RETRIES, last_exc)
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

    Returns summary: {checked, confirmed, inserted, skipped_existing, errors, aborted}.

    Safety constraints applied on every run:
    - Wikipedia calls are capped at MAX_WIKIPEDIA_CALLS per execution.
    - If confirmed (would-insert) count exceeds MAX_INSERTS_PER_RUN, the entire
      run is aborted without writing any rows (safety brake).
    - dry_run=True prints a sample of up to 20 candidates with accept/reject reason.
    """
    from app.db import has_death_by_qid, is_already_dead, is_already_watched, upsert_global_death
    from app.filters import enrich_death

    if days_back is None:
        days_back = INGESTOR_WINDOW_DAYS

    summary: dict = {
        "checked": 0,
        "confirmed": 0,
        "inserted": 0,
        "skipped_existing": 0,
        "errors": 0,
        "aborted": False,
    }

    candidates = query_wikidata_deaths(days_back)
    log.info("Wikidata returned %d candidates (window=%d days)", len(candidates), days_back)

    # In dry_run mode, collect up to 20 sample decisions to print at the end.
    dry_run_sample: list[dict] = []
    wikipedia_calls = 0

    # First pass: evaluate all candidates, count confirms (safety brake pre-check).
    # We track them in a list to do a single write pass afterwards.
    pending_inserts: list[tuple[dict, str]] = []  # (candidate, death_date)

    for cand in candidates:
        summary["checked"] += 1
        qid = cand["qid"]
        wiki_title = cand["wiki_title"]

        try:
            if is_already_watched(wiki_title):
                summary["skipped_existing"] += 1
                _dry_sample(dry_run_sample, wiki_title, qid, "SKIP: already watched")
                continue
            if has_death_by_qid(qid) or is_already_dead(wiki_title):
                summary["skipped_existing"] += 1
                _dry_sample(dry_run_sample, wiki_title, qid, "SKIP: already in DB")
                continue

            if wikipedia_calls >= MAX_WIKIPEDIA_CALLS:
                _dry_sample(dry_run_sample, wiki_title, qid, "SKIP: Wikipedia call limit reached")
                log.warning(
                    "Wikipedia call limit (%d) reached; stopping evaluation at %d/%d checked",
                    MAX_WIKIPEDIA_CALLS, summary["checked"], len(candidates),
                )
                break

            if not _OFFLINE_MODE:
                wikipedia_calls += 1
            confirmed, death_date = confirm_death(cand)

            if not confirmed:
                _dry_sample(dry_run_sample, wiki_title, qid, "REJECT: death not confirmed by Wikipedia")
                continue

            summary["confirmed"] += 1
            _dry_sample(dry_run_sample, wiki_title, qid, f"ACCEPT: death_date={death_date}")
            pending_inserts.append((cand, death_date))

        except Exception as exc:
            log.error("Error evaluating %s (%s): %s", wiki_title, qid, exc)
            summary["errors"] += 1

    # Safety brake: abort before writing if too many new deaths in one run.
    if len(pending_inserts) > MAX_INSERTS_PER_RUN:
        log.error(
            "SAFETY BRAKE: %d confirmed deaths exceed MAX_INSERTS_PER_RUN=%d — "
            "aborting without writing. Investigate before re-running.",
            len(pending_inserts), MAX_INSERTS_PER_RUN,
        )
        summary["aborted"] = True
        _print_dry_run_sample(dry_run_sample)
        return summary

    if dry_run:
        _print_dry_run_sample(dry_run_sample)
        log.info(
            "[DRY-RUN] Would insert %d death(s). "
            "Re-run without --dry-run to commit.",
            len(pending_inserts),
        )
        return summary

    # Write pass.
    for cand, death_date in pending_inserts:
        qid = cand["qid"]
        wiki_title = cand["wiki_title"]
        wiki_url = f"https://en.wikipedia.org/wiki/{wiki_title}"
        try:
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
            log.error("Error inserting %s (%s): %s", wiki_title, qid, exc)
            summary["errors"] += 1

    log.info(
        "Ingestor complete: checked=%d confirmed=%d inserted=%d "
        "skipped_existing=%d errors=%d wikipedia_calls=%d aborted=%s",
        summary["checked"], summary["confirmed"], summary["inserted"],
        summary["skipped_existing"], summary["errors"], wikipedia_calls,
        summary["aborted"],
    )
    return summary


def _dry_sample(sample: list[dict], wiki_title: str, qid: str, reason: str) -> None:
    """Append to dry-run sample (capped at 20 entries)."""
    if len(sample) < 20:
        sample.append({"wiki_title": wiki_title, "qid": qid, "reason": reason})


def _print_dry_run_sample(sample: list[dict]) -> None:
    if not sample:
        return
    log.info("[DRY-RUN] Sample of up to 20 candidates evaluated:")
    for i, entry in enumerate(sample, 1):
        log.info(
            "[DRY-RUN] %2d. %-40s (%s) — %s",
            i, entry["wiki_title"], entry["qid"], entry["reason"],
        )


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
