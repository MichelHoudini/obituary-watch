"""
Tests for app/main.py: date formatting for display, and a smoke test of the
main public routes via FastAPI's TestClient.
"""
from fastapi.testclient import TestClient

from app.main import app, format_death_date

# ── format_death_date ────────────────────────────────────────────────────

def test_formats_a_real_death_date_template():
    raw = "{{Death date and age|2025|10|1|1934|4|3|df=y}}"
    assert format_death_date(raw) == "October 1, 2025"


def test_formats_without_the_optional_df_flag():
    raw = "{{Death date and age|2026|7|20|1930|5|31}}"
    assert format_death_date(raw) == "July 20, 2026"


def test_placeholder_comment_falls_back_unchanged_by_design():
    """format_death_date's contract is 'parse a real date template, else
    pass the value through unchanged' -- it is NOT the layer responsible
    for rejecting Wikipedia's placeholder comment; that's
    watcher.extract_death_date's job (see test_watcher.py), which stops
    this value from ever being stored in the first place. If this
    unrecognized-shape string ever did reach here, passing it through
    unchanged (not hiding it, not crashing) is the correct, safe fallback --
    the actual XSS-safety net is e()'s HTML-escaping at render time, not
    this function."""
    raw = "<!-- {{Death date and age|YYYY|MM|DD|YYYY|MM|DD}} (DEATH date then BIRTH date) -->"
    assert format_death_date(raw) == raw


def test_none_returns_confirmed():
    assert format_death_date(None) == "confirmed"


def test_empty_string_returns_confirmed():
    assert format_death_date("") == "confirmed"


def test_unrecognized_value_falls_back_unchanged():
    raw = "sometime in the autumn, exact date disputed"
    assert format_death_date(raw) == raw


def test_simple_death_date_template_without_and_age():
    assert format_death_date("{{Death date|2020|3|15}}") == "March 15, 2020"


def test_invalid_month_falls_back_to_raw():
    """Guards against an out-of-range month (e.g. a data entry error
    upstream on Wikipedia) producing a nonsense formatted date."""
    raw = "{{Death date and age|2026|13|1|1930|5|31}}"
    assert format_death_date(raw) == raw


# ── route smoke tests ────────────────────────────────────────────────────

client = TestClient(app)


def test_homepage_returns_200():
    r = client.get("/")
    assert r.status_code == 200


def test_people_directory_returns_200():
    r = client.get("/people")
    assert r.status_code == 200


def test_deaths_log_returns_200():
    r = client.get("/deaths")
    assert r.status_code == 200


def test_api_deaths_returns_json():
    r = client.get("/api/deaths")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


def test_status_returns_watcher_health_shape():
    r = client.get("/status")
    assert r.status_code == 200
    body = r.json()
    assert "watcher_health" in body
    assert "watcher_is_stale" in body
    assert "watching" in body
    assert "deaths_detected" in body


def test_sitemap_is_xml():
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert "xml" in r.headers["content-type"]
    assert r.text.startswith("<?xml")


def test_robots_txt_points_at_sitemap():
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "sitemap.xml" in r.text.lower()


def test_unknown_route_is_404():
    r = client.get("/this-route-does-not-exist")
    assert r.status_code == 404


def test_watch_endpoint_rate_limits_after_five_calls_per_minute():
    """Matches the 5/minute/IP limit added after this endpoint (the only one
    that writes to the DB and sends a real email on every call) shipped with
    no abuse protection. All calls in this test share TestClient's fixed
    client IP, so they count against the same bucket -- kept self-contained
    in one test rather than spread across the file, since slowapi's counter
    state persists for the whole test session, not per-test."""
    statuses = []
    for i in range(7):
        r = client.post(
            "/watch",
            json={"wiki_title": f"Rate_Limit_Test_{i}", "email": f"test{i}@example.com"},
        )
        statuses.append(r.status_code)

    assert statuses[:5] == [200] * 5
    assert 429 in statuses[5:]
