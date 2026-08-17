"""
Tests for app/db.py. Runs against an isolated per-test SQLite file
(see conftest.py) -- never touches Postgres or any real data.
"""
from app.db import (
    add_watch,
    add_watched,
    get_all_watched_titles,
    get_death_count,
    get_deaths,
    get_emails_for,
    get_watch_count_for_title,
    get_watch_counts,
    get_watcher_health,
    is_already_dead,
    record_death,
    record_watcher_error,
    record_watcher_event,
    record_watcher_heartbeat,
    record_watcher_start,
    remove_false_death_detections,
)

# ── watched titles (public catalog) ──────────────────────────────────────

def test_add_watched_then_appears_in_all_watched_titles():
    add_watched("Test_Person", "Test Person", "Actors", 1980)
    assert "Test_Person" in get_all_watched_titles()


def test_add_watched_is_idempotent():
    """Seeding the same catalog entry twice (e.g. app restart) must not
    duplicate it or raise."""
    add_watched("Test_Person", "Test Person", "Actors", 1980)
    add_watched("Test_Person", "Test Person", "Actors", 1980)
    titles = [t for t in get_all_watched_titles() if t == "Test_Person"]
    assert len(titles) == 1


# ── real email subscriptions ─────────────────────────────────────────────

def test_add_watch_creates_a_real_subscription():
    is_new = add_watch("Test_Person", "someone@example.com")
    assert is_new is True
    assert "someone@example.com" in get_emails_for("Test_Person")


def test_add_watch_same_email_twice_is_not_new():
    add_watch("Test_Person", "someone@example.com")
    is_new_again = add_watch("Test_Person", "someone@example.com")
    assert is_new_again is False


def test_seeding_catalog_never_creates_a_fake_subscription():
    """add_watched (catalog seed) and add_watch (real user subscription)
    must stay on separate tables -- seeding the catalog must never produce
    a fake email subscriber. get_watch_count() intentionally counts the
    union of both tables (that's what /status's "watching" total means),
    so the real assertion is on the watches table specifically, via
    get_emails_for."""
    add_watched("Test_Person", "Test Person", "Actors", 1980)
    assert get_emails_for("Test_Person") == []


def test_watch_counts_batch_matches_per_title_lookup():
    add_watch("Person_A", "a@example.com")
    add_watch("Person_A", "b@example.com")
    add_watch("Person_B", "c@example.com")
    counts = get_watch_counts()
    assert counts.get("Person_A") == get_watch_count_for_title("Person_A")
    assert counts.get("Person_B") == get_watch_count_for_title("Person_B")


# ── deaths ────────────────────────────────────────────────────────────────

def test_record_death_then_is_already_dead():
    assert is_already_dead("Test_Person") is False
    record_death("Test_Person", "Test Person", "{{Death date and age|2026|1|1|1930|1|1}}")
    assert is_already_dead("Test_Person") is True


def test_get_deaths_returns_recorded_death():
    record_death("Test_Person", "Test Person", "{{Death date and age|2026|1|1|1930|1|1}}")
    deaths = get_deaths(10)
    assert any(d["wiki_title"] == "Test_Person" for d in deaths)
    assert get_death_count() >= 1


def test_remove_false_death_detections_cleans_placeholder_only():
    """The exact regression this function exists to fix, at the DB layer:
    a row whose death_date is only Wikipedia's placeholder comment gets
    removed; a row with a real date survives."""
    record_death(
        "False_Positive",
        "False Positive",
        "<!-- {{Death date and age|YYYY|MM|DD|YYYY|MM|DD}} (DEATH date then BIRTH date) -->",
    )
    record_death("Real_Death", "Real Death", "{{Death date and age|2026|1|1|1930|1|1}}")

    removed = remove_false_death_detections()

    assert "False_Positive" in removed
    assert "Real_Death" not in removed
    assert is_already_dead("False_Positive") is False
    assert is_already_dead("Real_Death") is True


def test_remove_false_death_detections_is_a_no_op_when_nothing_bad():
    record_death("Real_Death", "Real Death", "{{Death date and age|2026|1|1|1930|1|1}}")
    assert remove_false_death_detections() == []


# ── watcher healthcheck ───────────────────────────────────────────────────

def test_watcher_health_starts_empty():
    assert get_watcher_health() is None


def test_watcher_start_then_heartbeat_updates_health():
    record_watcher_start()
    health = get_watcher_health()
    assert health is not None
    assert health["started_at"] is not None

    record_watcher_heartbeat()
    health = get_watcher_health()
    assert health["heartbeat_at"] is not None


def test_watcher_event_records_last_checked_title():
    record_watcher_start()
    record_watcher_event("Some_Title")
    health = get_watcher_health()
    assert health["last_checked_title"] == "Some_Title"


def test_watcher_error_is_truncated_and_stored():
    record_watcher_start()
    record_watcher_error("boom: connection reset")
    health = get_watcher_health()
    assert "boom" in health["last_error"]


def test_watcher_error_does_not_blow_up_on_huge_message():
    """record_watcher_error must truncate defensively so a runaway
    exception message can't bloat the row indefinitely."""
    record_watcher_start()
    record_watcher_error("x" * 10_000)
    health = get_watcher_health()
    assert len(health["last_error"]) <= 500
