"""
Tests for app/ingestion.py — global death ingestion.

All tests run in offline mode (conftest.py autouse fixture sets
_OFFLINE_MODE=True and loads tests/fixtures/wikidata_deaths.json).
No live Wikidata or Wikipedia calls.

IDs: ING-001 to ING-015
"""

import pytest

import app.ingestion as ingestion_module
from app.ingestion import confirm_death, query_wikidata_deaths, run

# ── ING-001: offline fixture returns expected candidates ─────────────────────

def test_ing001_fixture_returns_candidates():
    """query_wikidata_deaths in offline mode returns fixture records."""
    results = query_wikidata_deaths(days_back=3)
    assert isinstance(results, list)
    assert len(results) >= 1
    first = results[0]
    assert "qid" in first
    assert "wiki_title" in first
    assert "display_name" in first
    assert "death_date_raw" in first


# ── ING-002: confirmed death passes both checks ───────────────────────────────

def test_ing002_confirmed_death_passes():
    """Candidate with valid infobox date and not in Living people: confirmed."""
    candidate = {
        "qid": "Q_CONFIRMED_DEATH",
        "wiki_title": "Test_Person_Confirmed",
        "categories": ["Category:1940 births", "Category:2026 deaths"],
        "wikitext": (
            "{{Infobox person\n| death_date = {{Death date|2026|01|15}}\n}}"
        ),
    }
    ok, death_date = confirm_death(candidate)
    assert ok is True
    assert death_date is not None
    assert "2026" in death_date or "Death date" in death_date


# ── ING-003: living person rejected ──────────────────────────────────────────

def test_ing003_living_person_rejected():
    """Candidate in Category:Living people must be rejected."""
    candidate = {
        "qid": "Q_LIVING_PERSON",
        "wiki_title": "Test_Living_Person",
        "categories": ["Category:Living people"],
        "wikitext": "{{Infobox person\n| death_date = {{Death date|2026|01|15}}\n}}",
    }
    ok, death_date = confirm_death(candidate)
    assert ok is False
    assert death_date is None


# ── ING-004: empty wikitext rejected ─────────────────────────────────────────

def test_ing004_empty_wikitext_rejected():
    """Candidate with no wikitext must be rejected."""
    candidate = {
        "qid": "Q_NO_WIKITEXT",
        "wiki_title": "Test_No_Wikitext",
        "categories": ["Category:2026 deaths"],
        "wikitext": "",
    }
    ok, _ = confirm_death(candidate)
    assert ok is False


# ── ING-005: placeholder death_date rejected ─────────────────────────────────

def test_ing005_placeholder_death_date_rejected():
    """Candidate whose infobox death_date is only an HTML comment is rejected."""
    candidate = {
        "qid": "Q_BAD_DATE",
        "wiki_title": "Test_Bad_Date",
        "categories": ["Category:2026 deaths"],
        "wikitext": (
            "{{Infobox person\n"
            "| death_date = "
            "<!-- {{Death date and age|YYYY|MM|DD|YYYY|MM|DD}} -->\n}}"
        ),
    }
    ok, _ = confirm_death(candidate)
    assert ok is False


# ── ING-006: run() inserts confirmed deaths ───────────────────────────────────

def test_ing006_run_inserts_confirmed():
    """run() in offline mode inserts exactly the fixture records that pass both checks."""
    from app.db import get_death_for_title

    summary = run(days_back=3, dry_run=False)
    assert summary["errors"] == 0
    assert summary["inserted"] >= 1
    # The Q_CONFIRMED_DEATH fixture should be inserted
    row = get_death_for_title("Test_Person_Confirmed")
    assert row is not None
    assert row["wiki_qid"] == "Q_CONFIRMED_DEATH"


# ── ING-007: run() does not insert living people ─────────────────────────────

def test_ing007_run_skips_living_people():
    """run() must not insert the living-person fixture."""
    from app.db import get_death_for_title

    run(days_back=3, dry_run=False)
    row = get_death_for_title("Test_Living_Person")
    assert row is None


# ── ING-008: run() does not insert candidates without valid death date ────────

def test_ing008_run_skips_invalid_date():
    """run() must not insert candidates whose wikitext has no valid death date."""
    from app.db import get_death_for_title

    run(days_back=3, dry_run=False)
    row = get_death_for_title("Test_Bad_Date")
    assert row is None


# ── ING-009: idempotency — second run inserts nothing new ────────────────────

def test_ing009_idempotent():
    """Running the ingestor twice for the same window produces no duplicates."""
    s1 = run(days_back=3, dry_run=False)
    s2 = run(days_back=3, dry_run=False)
    assert s2["inserted"] == 0
    assert s2["skipped_existing"] >= s1["inserted"]


# ── ING-010: dry_run writes nothing ──────────────────────────────────────────

def test_ing010_dry_run_writes_nothing():
    """dry_run=True must not write any rows to the deaths table."""
    from app.db import get_death_for_title

    summary = run(days_back=3, dry_run=True)
    assert summary["confirmed"] >= 1
    assert summary["inserted"] == 0
    row = get_death_for_title("Test_Person_Confirmed")
    assert row is None


# ── ING-011: has_death_by_qid returns False initially ────────────────────────

def test_ing011_has_death_by_qid_initially_false():
    from app.db import has_death_by_qid
    assert has_death_by_qid("Q_CONFIRMED_DEATH") is False


# ── ING-012: has_death_by_qid returns True after insert ──────────────────────

def test_ing012_has_death_by_qid_after_insert():
    from app.db import has_death_by_qid

    run(days_back=3, dry_run=False)
    assert has_death_by_qid("Q_CONFIRMED_DEATH") is True


# ── ING-013: upsert_global_death returns True for new row ────────────────────

def test_ing013_upsert_returns_true_for_new():
    from app.db import upsert_global_death

    is_new = upsert_global_death(
        wiki_qid="Q_MANUAL_TEST",
        wiki_title="Manual_Test_Person",
        display_name="Manual Test Person",
        death_date="{{Death date|2026|06|01}}",
        wiki_url="https://en.wikipedia.org/wiki/Manual_Test_Person",
    )
    assert is_new is True


# ── ING-014: upsert_global_death is idempotent ───────────────────────────────

def test_ing014_upsert_idempotent():
    from app.db import upsert_global_death

    kwargs = dict(
        wiki_qid="Q_IDEMPOTENT_TEST",
        wiki_title="Idempotent_Test_Person",
        display_name="Idempotent Test Person",
        death_date="{{Death date|2026|05|01}}",
        wiki_url="https://en.wikipedia.org/wiki/Idempotent_Test_Person",
    )
    first = upsert_global_death(**kwargs)
    second = upsert_global_death(**kwargs)
    assert first is True
    assert second is False


# ── ING-015: run() summary keys are complete ─────────────────────────────────

def test_ing015_summary_has_all_keys():
    """run() always returns a dict with all five summary keys."""
    summary = run(days_back=3, dry_run=True)
    for key in ("checked", "confirmed", "inserted", "skipped_existing", "errors"):
        assert key in summary, f"Summary missing key: {key}"
        assert isinstance(summary[key], int)


# ── ING-016: ingestor skips watched titles (regression) ──────────────────────

def test_ing016_ingestor_skips_watched_title():
    """Watched title must be skipped by the ingestor so the watcher sends exactly
    one email when it later detects the death.

    Regression guard: if the ingestor inserts a death for a watched title first,
    the watcher's record_death() returns False (already exists) and the email
    is never sent.  The fix is is_already_watched() at the top of run()."""
    from app.db import add_watch_with_token, get_death_for_title, init_db

    init_db()
    # Mark the confirmed fixture title as watched.
    add_watch_with_token("Test_Person_Confirmed", "watcher@example.com")

    summary = run(days_back=3, dry_run=False)

    # Ingestor must not have inserted the watched title.
    assert summary["skipped_existing"] >= 1
    row = get_death_for_title("Test_Person_Confirmed")
    assert row is None, (
        "Ingestor inserted a watched title; "
        "is_already_watched() check may be missing from run()"
    )


# ── ING-017: safety brake aborts when >500 confirmed ─────────────────────────

def test_ing017_safety_brake():
    """run() must abort without writing when confirmed count > MAX_INSERTS_PER_RUN."""
    import app.ingestion as m

    # Patch MAX_INSERTS_PER_RUN to -1 so any confirmed death triggers the brake.
    original = m.MAX_INSERTS_PER_RUN
    m.MAX_INSERTS_PER_RUN = -1
    try:
        summary = run(days_back=3, dry_run=False)
    finally:
        m.MAX_INSERTS_PER_RUN = original

    assert summary["aborted"] is True
    assert summary["inserted"] == 0


# ── ING-018: dry_run includes aborted key ────────────────────────────────────

def test_ing018_summary_has_aborted_key():
    """run() must return an 'aborted' key."""
    summary = run(days_back=3, dry_run=True)
    assert "aborted" in summary
    assert summary["aborted"] is False
