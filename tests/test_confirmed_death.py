"""
Tests for is_confirmed_death() — canonical definition and all surfaces.

CONF-001 to CONF-010 cover the function itself and verify it is the single
definition used by nicho pages, watcher email path, and filter notification path.
"""

import pytest


# ── CONF-001 to CONF-005: is_confirmed_death() unit tests ────────────────────

def test_conf001_valid_death_date_template():
    from app.dates import is_confirmed_death
    assert is_confirmed_death("{{Death date|2026|01|15}}") is True


def test_conf002_death_date_and_age():
    from app.dates import is_confirmed_death
    assert is_confirmed_death("{{Death date and age|2026|6|1|1940|1|1}}") is True


def test_conf003_plain_year():
    from app.dates import is_confirmed_death
    assert is_confirmed_death("2026") is True


def test_conf004_html_comment_only_rejected():
    from app.dates import is_confirmed_death
    assert is_confirmed_death(
        "<!-- {{Death date and age|YYYY|MM|DD|YYYY|MM|DD}} -->"
    ) is False


def test_conf005_none_rejected():
    from app.dates import is_confirmed_death
    assert is_confirmed_death(None) is False


def test_conf006_empty_string_rejected():
    from app.dates import is_confirmed_death
    assert is_confirmed_death("") is False


def test_conf007_death_date_template_without_year_rejected():
    from app.dates import is_confirmed_death
    # Template present but no YYYY parameter
    assert is_confirmed_death("{{Death date}}") is False


# ── CONF-008: nicho page surface ─────────────────────────────────────────────

def test_conf008_nicho_page_excludes_unconfirmed_death():
    """_nicho_death_rows() must exclude deaths with a placeholder date."""
    from app.db import init_db, record_death
    from app.main import _nicho_death_rows

    init_db()
    record_death(
        "Placeholder_Death_Person",
        "Placeholder Death Person",
        "<!-- {{Death date and age|YYYY|MM|DD|YYYY|MM|DD}} -->",
    )
    record_death(
        "Confirmed_Nicho_Person",
        "Confirmed Nicho Person",
        "{{Death date|2026|03|10}}",
    )

    from app.db import get_deaths
    all_deaths = get_deaths(100)
    confirmed = _nicho_death_rows(all_deaths)

    titles = [d["wiki_title"] for d in confirmed]
    assert "Confirmed_Nicho_Person" in titles
    assert "Placeholder_Death_Person" not in titles


# ── CONF-009: filter notification surface ────────────────────────────────────

def test_conf009_filter_notification_skips_unconfirmed_death():
    """get_notifiable_emails_for_death() must not add filter-watch emails when
    the death_date is unconfirmed (placeholder HTML comment)."""
    from app.db import add_watch_with_token, init_db
    from app.filters import get_notifiable_emails_for_death

    init_db()
    add_watch_with_token(
        "Filter_Test_Person",
        "filter_watcher@example.com",
        filter_occupation_qid="Q36180",
    )

    unconfirmed_death = {
        "wiki_title": "Some_Unknown_Person",
        "death_date": "<!-- {{Death date and age|YYYY|MM|DD|YYYY|MM|DD}} -->",
        "occupation_qids": ["Q36180"],
        "location_qids": [],
    }

    emails = get_notifiable_emails_for_death("Some_Unknown_Person", unconfirmed_death)
    assert "filter_watcher@example.com" not in emails


def test_conf009b_filter_notification_includes_confirmed_death():
    """get_notifiable_emails_for_death() must include filter-watch emails when
    the death_date is confirmed and filter QIDs match (SQLite path)."""
    from app.db import add_watch_with_token, init_db
    from app.filters import get_notifiable_emails_for_death

    init_db()
    add_watch_with_token(
        "Filter_Confirmed_Person",
        "filter_confirmed@example.com",
        filter_occupation_qid="Q36180",
    )

    confirmed_death = {
        "wiki_title": "Some_Confirmed_Person",
        "death_date": "{{Death date|2026|06|01}}",
        "occupation_qids": ["Q36180", "Q177220"],
        "location_qids": [],
    }

    emails = get_notifiable_emails_for_death("Some_Confirmed_Person", confirmed_death)
    assert "filter_confirmed@example.com" in emails


# ── CONF-010: is_confirmed_death is imported from app.dates in main.py ───────

def test_conf010_nicho_rows_uses_canonical_is_confirmed_death():
    """_nicho_death_rows() must use app.dates.is_confirmed_death, not an
    inline re.search, so the single canonical definition is enforced."""
    import inspect

    from app.main import _nicho_death_rows
    source = inspect.getsource(_nicho_death_rows)
    assert "is_confirmed_death" in source, (
        "_nicho_death_rows() must call is_confirmed_death() from app.dates"
    )
