"""
filters.py — Wikidata enrichment and filter matching for Mortivox.

Adds occupation/location ancestor chains to detected deaths.
match_watch() decides whether a filter subscription should receive a notification.
Runs inside GitHub Actions watcher — never on Render (no live Wikidata calls there).
"""

import logging
import os
from datetime import UTC, datetime, timedelta

log = logging.getLogger(__name__)

ENRICHMENT_GRACE_HOURS: int = int(os.environ.get("ENRICHMENT_GRACE_HOURS", "24"))

# Module-level state populated by tests/conftest.py before each test run.
# In production these stay False/{} and the live Wikidata API is used.
_OFFLINE_MODE: bool = False
_WIKIDATA_GRAPH: dict[str, dict[str, list[str]]] = {}
_FIXTURE_ENTITIES: dict[str, dict] = {}

WIKIDATA_API = "https://www.wikidata.org/w/api.php"


def traverse_hierarchy(qid: str, prop: str, max_depth: int = 10) -> list[str]:
    """Return [qid] + all ancestors via prop (P279 or P131).

    Stops at max_depth levels or when a QID is seen a second time (cycle).
    Result starts with the direct qid; no duplicates.
    """
    visited: set[str] = set()
    result: list[str] = []

    def _walk(current: str, depth: int) -> None:
        if depth > max_depth or current in visited:
            return
        visited.add(current)
        result.append(current)
        if _OFFLINE_MODE:
            parents = _WIKIDATA_GRAPH.get(current, {}).get(prop, [])
        else:
            parents = _fetch_parents(current, prop)
        for parent in parents:
            _walk(parent, depth + 1)

    _walk(qid, 0)
    return result


def _fetch_parents(qid: str, prop: str) -> list[str]:
    try:
        import requests  # noqa: PLC0415
        r = requests.get(WIKIDATA_API, params={
            "action": "wbgetentities",
            "ids": qid,
            "props": "claims",
            "format": "json",
        }, timeout=10)
        entity = r.json().get("entities", {}).get(qid, {})
        claims = entity.get("claims", {}).get(prop, [])
        return [
            c["mainsnak"]["datavalue"]["value"]["id"]
            for c in claims
            if c.get("mainsnak", {}).get("snaktype") == "value"
            and c["mainsnak"].get("datavalue", {}).get("type") == "wikibase-entityid"
        ]
    except Exception as exc:
        log.warning("Wikidata fetch failed for %s/%s: %s", qid, prop, exc)
        return []


def match_watch(watch: dict, death: dict) -> bool:
    """Return True if watch's filter(s) match the death's ancestor arrays.

    Requires at least one filter QID set; returns False for no-filter watches
    (those are person-specific and handled by get_emails_for).
    AND logic: every non-null filter must match.
    Never raises; returns False on any unexpected input.
    """
    try:
        occ_filter = watch.get("filter_occupation_qid")
        loc_filter = watch.get("filter_location_qid")

        if not occ_filter and not loc_filter:
            return False

        death_occs = death.get("occupation_qids") or []
        death_locs = death.get("location_qids") or []

        if occ_filter and occ_filter not in death_occs:
            return False
        if loc_filter and loc_filter not in death_locs:
            return False
        return True
    except Exception:
        return False


def enrich_death(wiki_title: str) -> dict:
    """Fetch Wikidata for wiki_title and build occupation/location ancestor chains.

    Returns {"occupation_qids": [...], "location_qids": [...]}.
    Also persists to DB if the death row exists.
    Arrays are always lists (never None); empty when data absent.
    """
    occupation_qids: list[str] = []
    location_qids: list[str] = []

    if _OFFLINE_MODE and wiki_title in _FIXTURE_ENTITIES:
        data = _FIXTURE_ENTITIES[wiki_title]
        occupation_qids = list(data.get("occupation_qids", []))
        location_qids = list(data.get("location_qids", []))
        _try_update_db(wiki_title, occupation_qids, location_qids)
        return {"occupation_qids": occupation_qids, "location_qids": location_qids}

    if not _OFFLINE_MODE:
        raw_occs, raw_locs = _fetch_person_claims(wiki_title)
        seen_occ: set[str] = set()
        for occ_qid in raw_occs:
            for anc in traverse_hierarchy(occ_qid, "P279"):
                if anc not in seen_occ:
                    seen_occ.add(anc)
                    occupation_qids.append(anc)
        seen_loc: set[str] = set()
        for loc_qid in raw_locs:
            for anc in traverse_hierarchy(loc_qid, "P131"):
                if anc not in seen_loc:
                    seen_loc.add(anc)
                    location_qids.append(anc)

    _try_update_db(wiki_title, occupation_qids, location_qids)
    return {"occupation_qids": occupation_qids, "location_qids": location_qids}


def _try_update_db(wiki_title: str, occupation_qids: list, location_qids: list) -> None:
    try:
        from app.db import update_death_enrichment  # noqa: PLC0415
        update_death_enrichment(wiki_title, occupation_qids, location_qids)
    except Exception as exc:
        log.warning("Could not persist enrichment for %s: %s", wiki_title, exc)


def _fetch_person_claims(wiki_title: str) -> tuple[list[str], list[str]]:
    try:
        import requests  # noqa: PLC0415
        r = requests.get("https://en.wikipedia.org/w/api.php", params={
            "action": "query",
            "titles": wiki_title,
            "prop": "pageprops",
            "ppprop": "wikibase_item",
            "format": "json",
        }, timeout=10)
        pages = r.json().get("query", {}).get("pages", {})
        page: dict = next(iter(pages.values()), {})
        qid = page.get("pageprops", {}).get("wikibase_item")
        if not qid:
            return [], []

        r2 = requests.get(WIKIDATA_API, params={
            "action": "wbgetentities",
            "ids": qid,
            "props": "claims",
            "format": "json",
        }, timeout=10)
        entity = r2.json().get("entities", {}).get(qid, {})
        claims = entity.get("claims", {})

        def _qids(prop: str) -> list[str]:
            return [
                c["mainsnak"]["datavalue"]["value"]["id"]
                for c in claims.get(prop, [])
                if c.get("mainsnak", {}).get("snaktype") == "value"
                and c["mainsnak"].get("datavalue", {}).get("type") == "wikibase-entityid"
            ]

        return _qids("P106"), _qids("P20")
    except Exception as exc:
        log.warning("Wikidata claims fetch failed for %s: %s", wiki_title, exc)
        return [], []


def should_notify_filter_watch(detected_at: str, now: datetime | None = None) -> bool:
    """Return True if ENRICHMENT_GRACE_HOURS have elapsed since detected_at."""
    try:
        if now is None:
            now = datetime.now(UTC)
        if isinstance(detected_at, str):
            detected = datetime.fromisoformat(detected_at)
            if detected.tzinfo is None:
                detected = detected.replace(tzinfo=UTC)
        else:
            detected = detected_at
        return (now - detected) >= timedelta(hours=ENRICHMENT_GRACE_HOURS)
    except Exception:
        return False


def get_notifiable_emails_for_death(wiki_title: str, death: dict) -> set[str]:
    """Combine person-watch and filter-watch emails for a death, deduplicated.

    Guards against unconfirmed death_date values so that a death ingested
    before wikitext confirmation (e.g. from a partial Wikidata entry) never
    triggers filter-watch notifications.  Person-specific watches are not
    guarded here — they are sent by the watcher, which already validates
    the date via extract_death_date() before recording.
    """
    from app.dates import is_confirmed_death  # noqa: PLC0415
    from app.db import (  # noqa: PLC0415
        USE_POSTGRES,
        get_emails_for,
        get_filter_emails_for_death,
        get_filter_watches,
    )

    emails: set[str] = set()
    for email in get_emails_for(wiki_title):
        emails.add(email)

    if not is_confirmed_death(death.get("death_date")):
        return emails  # don't send filter notifications for unconfirmed deaths

    occ_qids = death.get("occupation_qids") or []
    loc_qids  = death.get("location_qids")  or []

    if USE_POSTGRES:
        for email in get_filter_emails_for_death(occ_qids, loc_qids):
            emails.add(email)
    else:
        for watch in get_filter_watches():
            if match_watch(watch, death):
                emails.add(watch["email"])
    return emails
