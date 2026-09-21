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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.db import init_db
    init_db()
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
