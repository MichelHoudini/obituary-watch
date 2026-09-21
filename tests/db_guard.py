"""
Safety guard: prevent test writes to remote or non-test databases.

URL resolution for test scripts (resolve_test_db_url):
  1. TEST_DATABASE_URL        (always preferred)
  2. DATABASE_URL             (only when env CI=true)

assert_test_db_safe() MUST be called before any TRUNCATE, DROP, or bulk
write in test code.  A safe URL requires:
  - hostname: localhost or 127.0.0.1
  - database name containing 'test' (e.g. mortivox_test)
"""

import os
import sys
from urllib.parse import urlparse


def _is_ci() -> bool:
    return os.environ.get("CI", "").lower() in ("true", "1", "yes")


def resolve_test_db_url() -> str | None:
    """Return the Postgres URL tests should use, or None (use SQLite).

    Reads TEST_DATABASE_URL first; falls back to DATABASE_URL only in CI
    (detected via CI=true set automatically by GitHub Actions).
    """
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url and _is_ci():
        url = os.environ.get("DATABASE_URL", "").strip()
    return url or None


def assert_test_db_safe(url: str) -> None:
    """Raise RuntimeError if url is not a safe local test database.

    Aborts with a clear message before any write reaches the database.
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        dbname = (parsed.path or "").lstrip("/")
    except Exception as exc:
        _abort(f"could not parse database URL: {exc}")
        return  # unreachable; _abort always raises

    if host not in ("localhost", "127.0.0.1"):
        _abort(
            f"host is '{host}' — only localhost/127.0.0.1 are allowed for "
            f"test writes. Set TEST_DATABASE_URL to a local test database."
        )

    if "test" not in dbname.lower():
        _abort(
            f"database '{dbname}' does not contain 'test' — refusing to write. "
            f"Rename your test database to include 'test' (e.g. mortivox_test)."
        )


def _abort(reason: str) -> None:
    msg = f"SAFETY ABORT: test DB guard blocked a write — {reason}"
    sys.stderr.write(msg + "\n")
    raise RuntimeError(msg)
