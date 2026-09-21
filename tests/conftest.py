"""
Shared test fixtures.

app/db.py's SQLite fallback writes to a relative path ("obituary_watch.db"
in the current working directory) when DATABASE_URL is unset. Rather than
change that (out of scope, and the relative-path behavior is fine for real
local dev), tests get isolation by running each test in its own temp
directory, so every test gets a fresh, empty SQLite file with no risk of
tests polluting each other or a developer's real local DB.
"""
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
