"""
Shared test fixtures.

app/db.py's SQLite fallback writes to a relative path ("obituary_watch.db"
in the current working directory) when DATABASE_URL is unset. Rather than
change that (out of scope, and the relative-path behavior is fine for real
local dev), tests get isolation by running each test in its own temp
directory, so every test gets a fresh, empty SQLite file with no risk of
tests polluting each other or a developer's real local DB.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ — for db_guard


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.db import DATABASE_URL, USE_POSTGRES, init_db
    if USE_POSTGRES:
        # Guard before any write: DATABASE_URL must be a local test database.
        from db_guard import assert_test_db_safe  # noqa: PLC0415
        assert_test_db_safe(DATABASE_URL)
    init_db()
    if USE_POSTGRES:
        # In CI all tests share one Postgres instance; truncate for isolation.
        from app.db import _exec, get_conn  # noqa: PLC0415
        with get_conn() as conn:
            for tbl in ("watches", "deaths", "monitored_titles", "watcher_health"):
                _exec(conn, f"TRUNCATE {tbl} RESTART IDENTITY CASCADE")
    yield


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset slowapi in-memory rate limit counters before each test.

    Without this, the 5/minute bucket on POST /watch is shared across
    the entire test session — adversarial tests that call /watch would
    exhaust it before test_main.py's rate-limit test runs.
    """
    try:
        from app.main import limiter
        limiter.reset()
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True)
def load_wikidata_fixtures():
    """Populate app.filters with versioned JSON fixtures before each test.

    Sets _OFFLINE_MODE=True so traverse_hierarchy and enrich_death never
    make live Wikidata calls. Restored to original state after each test.
    """
    try:
        import app.filters as filters_module

        fixtures_path = Path(__file__).parent / "fixtures" / "wikidata_hierarchy.json"
        data = json.loads(fixtures_path.read_text(encoding="utf-8"))

        old_graph    = dict(filters_module._WIKIDATA_GRAPH)
        old_entities = dict(filters_module._FIXTURE_ENTITIES)
        old_offline  = filters_module._OFFLINE_MODE

        filters_module._WIKIDATA_GRAPH    = data["graph"]
        filters_module._FIXTURE_ENTITIES  = data["entities"]
        filters_module._OFFLINE_MODE      = True

        yield

        filters_module._WIKIDATA_GRAPH    = old_graph
        filters_module._FIXTURE_ENTITIES  = old_entities
        filters_module._OFFLINE_MODE      = old_offline
    except ImportError:
        yield


@pytest.fixture(autouse=True)
def load_ingestion_fixtures():
    """Populate app.ingestion with versioned JSON fixtures before each test.

    Sets _OFFLINE_MODE=True so query_wikidata_deaths and confirm_death never
    make live network calls. Restored after each test.
    """
    try:
        import app.ingestion as ingestion_module

        fixtures_path = Path(__file__).parent / "fixtures" / "wikidata_deaths.json"
        data = json.loads(fixtures_path.read_text(encoding="utf-8"))

        old_offline  = ingestion_module._OFFLINE_MODE
        old_fixtures = list(ingestion_module._FIXTURE_DEATHS)

        ingestion_module._OFFLINE_MODE   = True
        ingestion_module._FIXTURE_DEATHS = data["deaths"]

        yield

        ingestion_module._OFFLINE_MODE   = old_offline
        ingestion_module._FIXTURE_DEATHS = old_fixtures
    except ImportError:
        yield
