"""
Migration tests (MIG-001 … MIG-005).

These tests require a real Postgres database and are skipped when
DATABASE_URL is not set (i.e., local SQLite runs).  In CI the quality job
sets DATABASE_URL so all five tests execute.

Isolation strategy: each test drops and recreates app tables via psycopg2
directly, bypassing the app fixtures.  After every test the tables are
restored to the current schema (init_db()) so subsequent tests are not
affected.

This module overrides the global `isolated_db` fixture so that DATABASE_URL
is NOT deleted — migration tests need Postgres.
"""

import logging
import os
import threading
from pathlib import Path

import pytest

# Captured at module-import time, before any fixture deletes it.
_POSTGRES_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL,
    reason="Postgres DATABASE_URL required (set by CI quality job)",
)

if _POSTGRES_URL:
    # Fail loud at collection time if the URL is not a safe local test DB.
    # conftest.py adds tests/ to sys.path before this module is imported.
    from db_guard import assert_test_db_safe as _assert_safe  # noqa: PLC0415, E402
    _assert_safe(_POSTGRES_URL)


# ---------------------------------------------------------------------------
# Override isolated_db for this module: keep DATABASE_URL intact.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Migration tests need the real Postgres URL — do NOT delete it."""
    monkeypatch.chdir(tmp_path)
    yield
    # Restore clean standard schema after each test so later tests are fine.
    _restore_current_schema()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _raw_conn():
    import psycopg2  # type: ignore[import]
    conn = psycopg2.connect(_POSTGRES_URL)
    conn.autocommit = True
    return conn


def _drop_all(conn) -> None:
    cur = conn.cursor()
    for idx in (
        "idx_deaths_occupation_qids",
        "idx_deaths_location_qids",
        "idx_deaths_wiki_qid",
        "idx_watches_cancel_token",
    ):
        cur.execute(f"DROP INDEX IF EXISTS {idx}")
    for tbl in ("watches", "deaths", "monitored_titles", "watcher_health"):
        cur.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")


def _create_legacy_schema(conn) -> None:
    """Create the pre-migration production schema (origin/master)."""
    sql = (
        Path(__file__).parent / "fixtures" / "schema_producao.sql"
    ).read_text(encoding="utf-8")
    conn.cursor().execute(sql)


def _restore_current_schema() -> None:
    conn = _raw_conn()
    _drop_all(conn)
    conn.close()
    from app.db import init_db, migrate_schema
    init_db()
    migrate_schema()  # recreate GIN indexes and other migration artifacts


def _col_names(conn, table: str) -> set[str]:
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
    """, (table,))
    return {r[0] for r in cur.fetchall()}


def _col_udt(conn, table: str, col: str) -> str | None:
    cur = conn.cursor()
    cur.execute("""
        SELECT udt_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
    """, (table, col))
    row = cur.fetchone()
    return row[0] if row else None


def _idx_exists(conn, idx_name: str) -> bool:
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = %s
    """, (idx_name,))
    return cur.fetchone() is not None


_NOW = "2024-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# MIG-001: fresh DB — init_db then migrate_schema twice, no error
# ---------------------------------------------------------------------------

def test_mig001_fresh_db_idempotent():
    from app.db import init_db, migrate_schema

    conn = _raw_conn()
    _drop_all(conn)
    conn.close()

    init_db()
    migrate_schema()  # first run: may be a no-op or apply changes
    migrate_schema()  # second run: must always be a no-op

    conn = _raw_conn()
    try:
        assert "filter_occupation_qid" in _col_names(conn, "watches")
        assert "cancel_token"          in _col_names(conn, "watches")
        assert "occupation_qids"       in _col_names(conn, "deaths")
        assert "location_qids"         in _col_names(conn, "deaths")
        assert "wiki_qid"              in _col_names(conn, "deaths")
        assert _col_udt(conn, "deaths", "occupation_qids") == "_text"
        assert _col_udt(conn, "deaths", "location_qids")   == "_text"
        assert _idx_exists(conn, "idx_deaths_occupation_qids")
        assert _idx_exists(conn, "idx_deaths_location_qids")
        assert _idx_exists(conn, "idx_deaths_wiki_qid")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# MIG-002: legacy schema with real rows — migrate and verify everything
# ---------------------------------------------------------------------------

def test_mig002_legacy_schema_with_data():
    from app.db import migrate_schema

    conn = _raw_conn()
    _drop_all(conn)
    _create_legacy_schema(conn)
    cur = conn.cursor()
    # watches without cancel_token (legacy)
    cur.execute(
        "INSERT INTO watches (wiki_title, email, created_at) VALUES (%s, %s, %s)",
        ("Pessoa_A", "a@example.com", _NOW),
    )
    cur.execute(
        "INSERT INTO watches (wiki_title, email, created_at) VALUES (%s, %s, %s)",
        ("Pessoa_B", "b@example.com", _NOW),
    )
    # death without arrays (legacy schema has no occupation_qids column)
    cur.execute(
        "INSERT INTO deaths (wiki_title, display_name, death_date, detected_at, wiki_url)"
        " VALUES (%s, %s, %s, %s, %s)",
        ("Pessoa_A", "Pessoa A", "2024-01-01", _NOW,
         "https://en.wikipedia.org/wiki/Pessoa_A"),
    )
    # Add occupation_qids column WITHOUT a default to simulate a partially-migrated
    # production database where some rows could have NULL (column added but not yet
    # backfilled).  This row will also have NULL after the manual ADD COLUMN.
    cur.execute("ALTER TABLE deaths ADD COLUMN occupation_qids TEXT")
    cur.execute("ALTER TABLE deaths ADD COLUMN location_qids TEXT")
    cur.execute(
        "INSERT INTO deaths (wiki_title, display_name, death_date, detected_at, wiki_url,"
        " occupation_qids, location_qids) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        ("Pessoa_Null", "Pessoa Null", "2024-01-01", _NOW,
         "https://en.wikipedia.org/wiki/Pessoa_Null", None, None),
    )
    conn.close()

    migrate_schema()

    conn = _raw_conn()
    try:
        # all migration columns present
        assert "filter_occupation_qid" in _col_names(conn, "watches")
        assert "filter_location_qid"   in _col_names(conn, "watches")
        assert "cancel_token"          in _col_names(conn, "watches")
        assert "occupation_qids"       in _col_names(conn, "deaths")
        assert "location_qids"         in _col_names(conn, "deaths")
        assert "wiki_qid"              in _col_names(conn, "deaths")

        # arrays are now TEXT[]
        assert _col_udt(conn, "deaths", "occupation_qids") == "_text"
        assert _col_udt(conn, "deaths", "location_qids")   == "_text"

        # NOT NULL constraint must be set after migration
        cur = conn.cursor()
        cur.execute("""
            SELECT is_nullable FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'deaths'
              AND column_name = 'occupation_qids'
        """)
        assert cur.fetchone()[0] == "NO", "occupation_qids must be NOT NULL after migration"
        cur.execute("""
            SELECT is_nullable FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'deaths'
              AND column_name = 'location_qids'
        """)
        assert cur.fetchone()[0] == "NO", "location_qids must be NOT NULL after migration"

        # GIN indexes created
        assert _idx_exists(conn, "idx_deaths_occupation_qids")
        assert _idx_exists(conn, "idx_deaths_location_qids")
        assert _idx_exists(conn, "idx_deaths_wiki_qid")

        # original data preserved
        cur.execute("SELECT COUNT(*) FROM deaths")
        assert cur.fetchone()[0] == 2

        # pre-migration row without arrays — got DEFAULT '[]' then converted to []
        cur.execute(
            "SELECT occupation_qids, location_qids FROM deaths WHERE wiki_title = %s",
            ("Pessoa_A",),
        )
        row = cur.fetchone()
        assert row[0] == [], "pre-migration row should have occupation_qids == []"
        assert row[1] == [], "pre-migration row should have location_qids == []"

        # pre-migration NULL row — NULL must become []
        cur.execute(
            "SELECT occupation_qids, location_qids FROM deaths WHERE wiki_title = %s",
            ("Pessoa_Null",),
        )
        row = cur.fetchone()
        assert row[0] == [], "NULL occupation_qids must become [] after migration"
        assert row[1] == [], "NULL location_qids must become [] after migration"

        # post-migration insert WITHOUT specifying arrays must get DEFAULT '{}'
        cur.execute(
            "INSERT INTO deaths (wiki_title, display_name, detected_at, wiki_url)"
            " VALUES (%s, %s, %s, %s)",
            ("Post_Migration", "Post Migration", _NOW,
             "https://en.wikipedia.org/wiki/Post_Migration"),
        )
        conn.commit()
        cur.execute(
            "SELECT occupation_qids, location_qids FROM deaths WHERE wiki_title = %s",
            ("Post_Migration",),
        )
        row = cur.fetchone()
        assert row[0] == [], "post-migration insert without arrays must get DEFAULT '{}'"
        assert row[1] == [], "post-migration insert without arrays must get DEFAULT '{}'"

        # cancel_token backfilled for all watches
        cur.execute("SELECT cancel_token FROM watches WHERE cancel_token IS NULL")
        assert cur.fetchone() is None
        cur.execute("SELECT COUNT(DISTINCT cancel_token) FROM watches")
        assert cur.fetchone()[0] == 2

        # second run must not change anything
        migrate_schema()
        cur.execute("SELECT cancel_token FROM watches WHERE cancel_token IS NULL")
        assert cur.fetchone() is None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# MIG-003: partial state — some columns exist, migration completes the rest
# ---------------------------------------------------------------------------

def test_mig003_partial_state_completes():
    from app.db import migrate_schema

    conn = _raw_conn()
    _drop_all(conn)
    _create_legacy_schema(conn)
    # Manually add ONE of the migration columns (simulating a partial run)
    conn.cursor().execute(
        "ALTER TABLE watches ADD COLUMN filter_occupation_qid TEXT"
    )
    conn.close()

    migrate_schema()

    conn = _raw_conn()
    try:
        cols = _col_names(conn, "watches")
        assert "filter_occupation_qid" in cols
        assert "filter_location_qid"   in cols
        assert "cancel_token"          in cols

        assert "occupation_qids" in _col_names(conn, "deaths")
        assert _idx_exists(conn, "idx_deaths_occupation_qids")
        assert _idx_exists(conn, "idx_deaths_location_qids")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# MIG-004: concurrent migrations — no error, no duplicate data
# ---------------------------------------------------------------------------

def test_mig004_concurrent_migrations():
    from app.db import migrate_schema

    conn = _raw_conn()
    _drop_all(conn)
    _create_legacy_schema(conn)
    conn.cursor().execute(
        "INSERT INTO watches (wiki_title, email, created_at) VALUES (%s, %s, %s)",
        ("Concurrent_Person", "c@example.com", _NOW),
    )
    conn.close()

    errors: list[str] = []

    def run_migrate():
        try:
            migrate_schema()
        except Exception as exc:
            errors.append(str(exc))

    t1 = threading.Thread(target=run_migrate)
    t2 = threading.Thread(target=run_migrate)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"Migration raised exceptions: {errors}"

    conn = _raw_conn()
    try:
        # The one watch must have exactly one non-NULL, unique cancel_token
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM watches WHERE cancel_token IS NOT NULL")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(DISTINCT cancel_token) FROM watches")
        assert cur.fetchone()[0] == 1
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# MIG-005: one step fails — other steps preserved, error names the step
# ---------------------------------------------------------------------------

def test_mig005_step_failure_isolated_and_named():
    """If occupation_qids contains non-JSON data the TYPE step fails;
    other steps (location_qids, indexes, cancel_token) still complete,
    and the log contains the step name."""
    from app.db import migrate_schema

    conn = _raw_conn()
    _drop_all(conn)
    _create_legacy_schema(conn)

    # Add occupation_qids as TEXT and poison one row with invalid JSON
    cur = conn.cursor()
    cur.execute("ALTER TABLE deaths ADD COLUMN occupation_qids TEXT DEFAULT '[]'")
    cur.execute(
        "INSERT INTO deaths (wiki_title, display_name, death_date, detected_at, "
        "wiki_url, occupation_qids) VALUES (%s, %s, %s, %s, %s, %s)",
        ("Bad_JSON_Person", "Bad JSON", "2024-01-01", _NOW,
         "https://en.wikipedia.org/wiki/Bad_JSON_Person", "NOT VALID JSON"),
    )
    # location_qids intentionally absent (will be added by migrate_schema)
    conn.close()

    log_records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            log_records.append(record)

    capture = _Capture()
    capture.setLevel(logging.DEBUG)
    db_logger = logging.getLogger("app.db")
    db_logger.addHandler(capture)
    try:
        migrate_schema()  # must not raise
    finally:
        db_logger.removeHandler(capture)

    conn = _raw_conn()
    try:
        deaths_cols = _col_names(conn, "deaths")
        watches_cols = _col_names(conn, "watches")

        # location_qids must have been added despite occupation_qids failure
        assert "location_qids" in deaths_cols
        # cancel_token must have been added in watches
        assert "cancel_token" in watches_cols
        # idx_deaths_wiki_qid must exist (independent step)
        assert _idx_exists(conn, "idx_deaths_wiki_qid")
    finally:
        conn.close()

    # The error log must mention the failing step name
    error_messages = [r.getMessage() for r in log_records if r.levelno >= logging.ERROR]
    assert any("occupation_qids" in m for m in error_messages), (
        f"Expected step name in error log, got: {error_messages}"
    )
