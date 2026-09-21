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


def _query_wikidata_range(from_dt: datetime, to_dt: datetime) -> list[dict]:
    """Core SPARQL query for an explicit [from_dt, to_dt) window.

    Returns rows sorted by death_date_raw descending (most recent first).
    Retries up to SPARQL_MAX_RETRIES times with exponential backoff.
    """
    import requests

    from_s = from_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    to_s   = to_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    sparql = _SPARQL_QUERY.format(from_date=from_s, to_date=to_s)

    last_exc: Exception | None = None
    data: dict = {}
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
        log.error("Wikidata SPARQL failed after %d attempts: %s", SPARQL_MAX_RETRIES, last_exc)
        return []

    results = []
    for row in data.get("results", {}).get("bindings", []):
        qid = _qid_from_uri(row.get("person", {}).get("value", ""))
        wiki_title = row.get("wikiTitle", {}).get("value", "").replace(" ", "_")
        label = row.get("personLabel", {}).get("value", wiki_title.replace("_", " "))
        death_date_raw = row.get("deathDate", {}).get("value", "")
        if qid and wiki_title:
            results.append({
                "qid": qid,
                "wiki_title": wiki_title,
                "display_name": label,
                "death_date_raw": death_date_raw,
            })

    # Stable order: most-recent deaths first so the call-limit always defers
    # the oldest unprocessed deaths, which are less likely to be confirmed fast.
    results.sort(key=lambda c: c.get("death_date_raw", ""), reverse=True)
    return results


def query_wikidata_deaths(days_back: int) -> list[dict]:
    """Return SPARQL rows for people who died in the last `days_back` days.

    In offline mode returns _FIXTURE_DEATHS (no sorting applied — fixtures
    are small and their order is deterministic).
    """
    if _OFFLINE_MODE:
        return [dict(d) for d in _FIXTURE_DEATHS]

    now     = datetime.now(UTC)
    from_dt = (now - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
    to_dt   = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return _query_wikidata_range(from_dt, to_dt)


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


# ─────────────────────────────────────────────────────────────────────────────
# Core evaluation/insertion logic, shared by run() and run_window().
# ─────────────────────────────────────────────────────────────────────────────

def _run_candidates(
    candidates: list[dict],
    max_wikipedia_calls: int,
    dry_run: bool,
) -> dict:
    """Evaluate and optionally persist `candidates`.

    Two-pass design:
      Pass 1 — DB checks only (no network).  Separates already-existing from new.
      Pass 2 — Wikipedia confirmation for up to max_wikipedia_calls new candidates.

    Always logs the dry-run summary line (total / already_in_db / will_call /
    deferred_by_limit) so callers can see what would happen even outside dry_run.

    Returns summary dict: checked, confirmed, inserted, skipped_existing, errors, aborted.
    """
    from app.db import has_death_by_qid, is_already_dead, is_already_watched, upsert_global_death
    from app.filters import enrich_death

    summary: dict = {
        "checked": 0,
        "confirmed": 0,
        "inserted": 0,
        "skipped_existing": 0,
        "errors": 0,
        "aborted": False,
    }

    # ── Pass 1: DB checks — no Wikipedia calls ────────────────────────────────
    new_candidates: list[dict] = []
    for cand in candidates:
        summary["checked"] += 1
        try:
            if (
                is_already_watched(cand["wiki_title"])
                or has_death_by_qid(cand["qid"])
                or is_already_dead(cand["wiki_title"])
            ):
                summary["skipped_existing"] += 1
            else:
                new_candidates.append(cand)
        except Exception as exc:
            log.error("DB check failed for %s (%s): %s", cand.get("wiki_title"), cand.get("qid"), exc)
            summary["errors"] += 1

    will_call_wiki = new_candidates[:max_wikipedia_calls]
    deferred_by_limit = new_candidates[max_wikipedia_calls:]

    log.info(
        "[INGESTOR] total=%d | already_in_db=%d | will_call_wiki=%d | deferred_next_run=%d",
        len(candidates),
        summary["skipped_existing"],
        len(will_call_wiki),
        len(deferred_by_limit),
    )

    # ── Pass 2: Wikipedia confirmation (runs even in dry_run to count confirmed) ─
    pending_inserts: list[tuple[dict, str | None]] = []
    for cand in will_call_wiki:
        try:
            confirmed, death_date = confirm_death(cand)
            if confirmed:
                summary["confirmed"] += 1
                pending_inserts.append((cand, death_date))
            if not _OFFLINE_MODE:
                time.sleep(0)  # yield; real throttle happens after upsert
        except Exception as exc:
            log.error("Wikipedia check failed for %s (%s): %s",
                      cand.get("wiki_title"), cand.get("qid"), exc)
            summary["errors"] += 1

    if dry_run:
        _print_dry_run_sample(will_call_wiki, deferred_by_limit, dry_run=True)
        log.info(
            "[DRY-RUN] confirmed=%d would-insert=%d — re-run without --dry-run to commit.",
            summary["confirmed"], len(pending_inserts),
        )
        return summary

    # ── Safety brake ─────────────────────────────────────────────────────────
    if len(pending_inserts) > MAX_INSERTS_PER_RUN:
        log.error(
            "SAFETY BRAKE: %d confirmed deaths exceed MAX_INSERTS_PER_RUN=%d — "
            "aborting without writing. Investigate before re-running.",
            len(pending_inserts), MAX_INSERTS_PER_RUN,
        )
        summary["aborted"] = True
        return summary

    # ── Write pass ───────────────────────────────────────────────────────────
    for cand, death_date in pending_inserts:
        qid        = cand["qid"]
        wiki_title = cand["wiki_title"]
        wiki_url   = f"https://en.wikipedia.org/wiki/{wiki_title}"
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
            log.error("Insert failed for %s (%s): %s", wiki_title, qid, exc)
            summary["errors"] += 1

    return summary


def _print_dry_run_sample(
    will_call: list[dict],
    deferred: list[dict],
    dry_run: bool = False,
) -> None:
    prefix = "[DRY-RUN]" if dry_run else "[INGESTOR]"
    sample = will_call[:20]
    if sample:
        log.info("%s Sample of up to 20 new candidates that would be confirmed:", prefix)
        for i, cand in enumerate(sample, 1):
            log.info(
                "%s %2d. %-40s (%s) death_date_raw=%s",
                prefix, i,
                cand.get("wiki_title", "?"),
                cand.get("qid", "?"),
                cand.get("death_date_raw", "?"),
            )
    if deferred:
        log.info(
            "%s %d candidate(s) deferred to next run (call limit).",
            prefix, len(deferred),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────────────────────────────────────

def run(days_back: int | None = None, dry_run: bool = False) -> dict:
    """Ingest confirmed deaths from Wikidata for the last `days_back` days.

    Returns summary: {checked, confirmed, inserted, skipped_existing, errors, aborted}.
    """
    if days_back is None:
        days_back = INGESTOR_WINDOW_DAYS

    candidates = query_wikidata_deaths(days_back)
    log.info("Wikidata returned %d candidates (window=%d days)", len(candidates), days_back)

    summary = _run_candidates(candidates, MAX_WIKIPEDIA_CALLS, dry_run)
    log.info(
        "run() complete: checked=%d confirmed=%d inserted=%d "
        "skipped_existing=%d errors=%d aborted=%s",
        summary["checked"], summary["confirmed"], summary["inserted"],
        summary["skipped_existing"], summary["errors"], summary["aborted"],
    )
    return summary


def run_window(
    from_dt: datetime,
    to_dt: datetime,
    max_wikipedia_calls: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Ingest deaths for an explicit date window.  Used by the backfill script.

    Args:
        from_dt: start of window (inclusive), UTC.
        to_dt:   end of window (exclusive), UTC.
        max_wikipedia_calls: override per-run call limit (default: MAX_WIKIPEDIA_CALLS).
        dry_run: if True, evaluate without writing.

    Returns the same summary dict as run().
    """
    if max_wikipedia_calls is None:
        max_wikipedia_calls = MAX_WIKIPEDIA_CALLS

    candidates = _query_wikidata_range(from_dt, to_dt)
    log.info(
        "run_window() [%s → %s]: %d candidates",
        from_dt.strftime("%Y-%m-%d"), to_dt.strftime("%Y-%m-%d"), len(candidates),
    )

    summary = _run_candidates(candidates, max_wikipedia_calls, dry_run)
    log.info(
        "run_window() complete: checked=%d confirmed=%d inserted=%d "
        "skipped_existing=%d errors=%d aborted=%s",
        summary["checked"], summary["confirmed"], summary["inserted"],
        summary["skipped_existing"], summary["errors"], summary["aborted"],
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
