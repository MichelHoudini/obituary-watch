"""
INT-040 – INT-044: filter subscription notification path.

Verifies that both the watcher and ingestor paths send exactly 1 email per
matching filter subscriber, 0 for non-matching deaths, and never duplicate on
repeated detection attempts.  Runs with SQLite (isolated_db) and offline
Wikidata (monkeypatched app.filters._OFFLINE_MODE).
"""
from unittest.mock import patch

import pytest

from app.db import add_watch, record_death
from app.filters import enrich_death, get_notifiable_emails_for_death

# ── INT-040: matching death triggers filter email ────────────────────────────

def test_int040_filter_email_sent_on_matching_death(monkeypatch):
    """After enrich_death(), get_notifiable_emails_for_death() includes the
    filter subscriber whose occupation_qid matches the death's ancestor chain."""
    import app.filters as flt
    monkeypatch.setattr(flt, "_OFFLINE_MODE", True)
    monkeypatch.setattr(flt, "_FIXTURE_ENTITIES", {
        "Musician_Test": {
            "occupation_qids": ["Q177220", "Q488205"],
            "location_qids": ["Q30"],
        }
    })

    add_watch("", "filter@example.com", filter_occupation_qid="Q177220")
    add_watch("Musician_Test", "fan@example.com")  # person-specific watch

    death_date = "{{Death date and age|2026|1|1|1940|1|1}}"
    record_death("Musician_Test", "Musician Test", death_date)
    enrichment = enrich_death("Musician_Test")

    death_record = {
        "occupation_qids": enrichment["occupation_qids"],
        "location_qids":   enrichment["location_qids"],
        "death_date":      death_date,
    }
    emails = get_notifiable_emails_for_death("Musician_Test", death_record)

    assert "filter@example.com" in emails, "filter subscriber must be notified"
    assert "fan@example.com" in emails, "person-specific subscriber must be notified"


# ── INT-041: non-matching death sends 0 filter emails ───────────────────────

def test_int041_no_email_on_non_matching_death(monkeypatch):
    """A death whose occupation does not match the subscriber's filter QID must
    not trigger any notification for that filter subscriber."""
    import app.filters as flt
    monkeypatch.setattr(flt, "_OFFLINE_MODE", True)
    monkeypatch.setattr(flt, "_FIXTURE_ENTITIES", {
        "Politician_Test": {
            "occupation_qids": ["Q82955"],  # politician — not a musician
            "location_qids": [],
        }
    })

    add_watch("", "musician_fan@example.com", filter_occupation_qid="Q177220")

    death_date = "{{Death date and age|2026|2|1|1950|1|1}}"
    record_death("Politician_Test", "Politician Test", death_date)
    enrichment = enrich_death("Politician_Test")

    death_record = {
        "occupation_qids": enrichment["occupation_qids"],
        "location_qids":   enrichment["location_qids"],
        "death_date":      death_date,
    }
    emails = get_notifiable_emails_for_death("Politician_Test", death_record)

    assert "musician_fan@example.com" not in emails, "non-matching death must not notify"


# ── INT-042: repeated detection never duplicates email ──────────────────────

def test_int042_repeated_watcher_detection_no_duplicate_email(monkeypatch):
    """record_death() returns False on second call for the same wiki_title.
    Simulating two watcher passes confirms only 1 email is sent in total."""
    import app.filters as flt
    monkeypatch.setattr(flt, "_OFFLINE_MODE", True)
    monkeypatch.setattr(flt, "_FIXTURE_ENTITIES", {
        "Repeat_Person": {
            "occupation_qids": ["Q177220"],
            "location_qids": [],
        }
    })

    add_watch("", "sub@example.com", filter_occupation_qid="Q177220")
    death_date = "{{Death date and age|2026|3|1|1945|1|1}}"
    email_calls: list[str] = []

    def fake_send(to_email, person_name, wiki_title, death_date, wiki_url,
                  edit_url=None, cancel_token=None):
        email_calls.append(to_email)
        return True

    with patch("app.email.send_death_notification", side_effect=fake_send):
        # First watcher pass
        is_new1 = record_death("Repeat_Person", "Repeat Person", death_date)
        if is_new1:
            enrichment = enrich_death("Repeat_Person")
            death_record = {
                "occupation_qids": enrichment["occupation_qids"],
                "location_qids":   enrichment["location_qids"],
                "death_date":      death_date,
            }
            from app.email import send_death_notification
            for em in get_notifiable_emails_for_death("Repeat_Person", death_record):
                send_death_notification(em, "Repeat Person", "Repeat_Person",
                                        death_date, "https://en.wikipedia.org/wiki/Repeat_Person")

        # Second watcher pass (same death detected again)
        is_new2 = record_death("Repeat_Person", "Repeat Person", death_date)
        if is_new2:  # must be False
            for em in get_notifiable_emails_for_death("Repeat_Person", {}):
                send_death_notification(em, "Repeat Person", "Repeat_Person",
                                        death_date, "https://en.wikipedia.org/wiki/Repeat_Person")

    assert is_new1 is True
    assert is_new2 is False
    assert len(email_calls) == 1, f"expected 1 email, got {len(email_calls)}"


# ── INT-043: watcher path uses get_notifiable_emails_for_death ──────────────

def test_int043_watcher_notifies_filter_subscriber(monkeypatch):
    """End-to-end: simulate the fixed watcher path. get_notifiable_emails_for_death
    is called (not just get_emails_for), so filter subscribers receive the email."""
    import app.filters as flt
    monkeypatch.setattr(flt, "_OFFLINE_MODE", True)
    monkeypatch.setattr(flt, "_FIXTURE_ENTITIES", {
        "Watcher_Path_Person": {
            "occupation_qids": ["Q177220"],
            "location_qids": ["Q30"],
        }
    })

    add_watch("", "watcher_filter@example.com", filter_occupation_qid="Q177220")
    death_date = "{{Death date and age|2026|4|1|1960|1|1}}"
    email_calls: list[str] = []

    def fake_send(to_email, person_name, wiki_title, death_date, wiki_url,
                  edit_url=None, cancel_token=None):
        email_calls.append(to_email)
        return True

    with patch("app.email.send_death_notification", side_effect=fake_send):
        from app.db import get_cancel_tokens_for_wiki
        is_new = record_death("Watcher_Path_Person", "Watcher Path Person", death_date)
        assert is_new is True
        enrichment = enrich_death("Watcher_Path_Person")
        death_record = {
            "occupation_qids": enrichment["occupation_qids"],
            "location_qids":   enrichment["location_qids"],
            "death_date":      death_date,
        }
        all_emails = list(get_notifiable_emails_for_death("Watcher_Path_Person", death_record))
        tokens = get_cancel_tokens_for_wiki("Watcher_Path_Person")
        from app.email import send_death_notification
        for em in all_emails:
            send_death_notification(
                to_email=em,
                person_name="Watcher Path Person",
                wiki_title="Watcher_Path_Person",
                death_date=death_date,
                wiki_url="https://en.wikipedia.org/wiki/Watcher_Path_Person",
                cancel_token=tokens.get(em),
            )

    assert "watcher_filter@example.com" in email_calls, (
        "filter subscriber must receive email via watcher path"
    )


# ── INT-044: ingestor path notifies filter subscriber ───────────────────────

def test_int044_ingestor_notifies_filter_subscriber(monkeypatch):
    """_notify_filter_subscribers() (called by ingestor after enrich_death) sends
    emails to matching filter subscribers."""
    import app.filters as flt
    monkeypatch.setattr(flt, "_OFFLINE_MODE", True)
    monkeypatch.setattr(flt, "_FIXTURE_ENTITIES", {
        "Ingestor_Person": {
            "occupation_qids": ["Q177220"],
            "location_qids": [],
        }
    })

    add_watch("", "ingestor_filter@example.com", filter_occupation_qid="Q177220")
    email_calls: list[str] = []

    def fake_send(to_email, person_name, wiki_title, death_date, wiki_url,
                  edit_url=None, cancel_token=None):
        email_calls.append(to_email)
        return True

    with patch("app.email.send_death_notification", side_effect=fake_send):
        from app.ingestion import _notify_filter_subscribers
        enrichment = {"occupation_qids": ["Q177220"], "location_qids": []}
        _notify_filter_subscribers(
            wiki_title="Ingestor_Person",
            display_name="Ingestor Person",
            death_date="{{Death date|2026|5|1}}",
            wiki_url="https://en.wikipedia.org/wiki/Ingestor_Person",
            enrichment=enrichment,
        )

    assert "ingestor_filter@example.com" in email_calls, (
        "filter subscriber must receive email via ingestor path"
    )
