"""
db.py - Database layer using PostgreSQL (Supabase/Render-compatible).
Falls back to SQLite for local development if DATABASE_URL is not set.
"""

import os
import logging
from datetime import datetime, timezone
from contextlib import contextmanager

log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    if USE_POSTGRES:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect("obituary_watch.db")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _exec(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def _fetchall(cur):
    rows = cur.fetchall()
    if not rows:
        return []
    if USE_POSTGRES:
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]
    return [dict(r) for r in rows]


def _fetchone(cur):
    row = cur.fetchone()
    if row is None:
        return None
    if USE_POSTGRES:
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))
    return dict(row)


def _ph():
    return "%s" if USE_POSTGRES else "?"


def init_db():
    with get_conn() as conn:
        if USE_POSTGRES:
            _exec(conn, """
                CREATE TABLE IF NOT EXISTS watches (
                    id         SERIAL PRIMARY KEY,
                    wiki_title TEXT NOT NULL,
                    email      TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(wiki_title, email)
                )
            """)
            _exec(conn, """
                CREATE TABLE IF NOT EXISTS monitored_titles (
                    id           SERIAL PRIMARY KEY,
                    wiki_title   TEXT UNIQUE NOT NULL,
                    display_name TEXT,
                    category     TEXT,
                    birth_year   INTEGER,
                    created_at   TEXT NOT NULL
                )
            """)
            _exec(conn, """
                CREATE TABLE IF NOT EXISTS deaths (
                    id           SERIAL PRIMARY KEY,
                    wiki_title   TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    death_date   TEXT,
                    detected_at  TEXT NOT NULL,
                    wiki_url     TEXT NOT NULL,
                    edit_url     TEXT
                )
            """)
            _exec(conn, """
                CREATE TABLE IF NOT EXISTS watcher_health (
                    key                 TEXT PRIMARY KEY,
                    started_at          TEXT,
                    heartbeat_at        TEXT,
                    last_event_at       TEXT,
                    last_checked_title  TEXT,
                    last_error          TEXT,
                    updated_at          TEXT
                )
            """)
        else:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS watches (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    wiki_title  TEXT NOT NULL,
                    email       TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    UNIQUE(wiki_title, email)
                );
                CREATE TABLE IF NOT EXISTS monitored_titles (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    wiki_title   TEXT UNIQUE NOT NULL,
                    display_name TEXT,
                    category     TEXT,
                    birth_year   INTEGER,
                    created_at   TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS deaths (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    wiki_title   TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    death_date   TEXT,
                    detected_at  TEXT NOT NULL,
                    wiki_url     TEXT NOT NULL,
                    edit_url     TEXT
                );
                CREATE TABLE IF NOT EXISTS watcher_health (
                    key                 TEXT PRIMARY KEY,
                    started_at          TEXT,
                    heartbeat_at        TEXT,
                    last_event_at       TEXT,
                    last_checked_title  TEXT,
                    last_error          TEXT,
                    updated_at          TEXT
                );
            """)


def add_watched(wiki_title: str, display_name: str = None, category: str = None, birth_year: int = None) -> bool:
    wiki_title = wiki_title.strip().replace(" ", "_")
    display_name = display_name or wiki_title.replace("_", " ")
    with get_conn() as conn:
        if USE_POSTGRES:
            _exec(conn, """
                INSERT INTO monitored_titles (wiki_title, display_name, category, birth_year, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (wiki_title) DO UPDATE SET
                    display_name = COALESCE(EXCLUDED.display_name, monitored_titles.display_name),
                    category = COALESCE(EXCLUDED.category, monitored_titles.category),
                    birth_year = COALESCE(EXCLUDED.birth_year, monitored_titles.birth_year)
            """, (wiki_title, display_name, category, birth_year, utcnow()))
        else:
            _exec(conn, """
                INSERT INTO monitored_titles (wiki_title, display_name, category, birth_year, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(wiki_title) DO UPDATE SET
                    display_name = COALESCE(excluded.display_name, monitored_titles.display_name),
                    category = COALESCE(excluded.category, monitored_titles.category),
                    birth_year = COALESCE(excluded.birth_year, monitored_titles.birth_year)
            """, (wiki_title, display_name, category, birth_year, utcnow()))
    return True


def add_watch(wiki_title: str, email: str) -> bool:
    wiki_title = wiki_title.strip().replace(" ", "_")
    email = email.strip().lower()
    add_watched(wiki_title, wiki_title.replace("_", " "), "User-monitored page", None)
    with get_conn() as conn:
        if USE_POSTGRES:
            cur = _exec(conn, """
                INSERT INTO watches (wiki_title, email, created_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (wiki_title, email) DO NOTHING
                RETURNING id
            """, (wiki_title, email, utcnow()))
            return _fetchone(cur) is not None
        else:
            cur = _exec(conn, """
                INSERT OR IGNORE INTO watches (wiki_title, email, created_at)
                VALUES (?, ?, ?)
            """, (wiki_title, email, utcnow()))
            return cur.rowcount > 0


def get_emails_for(wiki_title: str) -> list[str]:
    with get_conn() as conn:
        ph = _ph()
        cur = _exec(conn, f"SELECT email FROM watches WHERE wiki_title={ph}", (wiki_title,))
        rows = _fetchall(cur)
    return [r["email"] for r in rows]


def get_all_watched_titles() -> set[str]:
    with get_conn() as conn:
        cur = _exec(conn, """
            SELECT wiki_title FROM monitored_titles
            UNION
            SELECT wiki_title FROM watches
        """)
        rows = _fetchall(cur)
    return {r["wiki_title"] for r in rows}


def get_monitored_people(limit: int = 500) -> list[dict]:
    with get_conn() as conn:
        ph = _ph()
        cur = _exec(conn, f"""
            SELECT wiki_title, display_name, category, birth_year, created_at
            FROM monitored_titles
            ORDER BY display_name ASC
            LIMIT {ph}
        """, (limit,))
        return _fetchall(cur)


def get_watch_count() -> int:
    with get_conn() as conn:
        cur = _exec(conn, """
            SELECT COUNT(*) AS n FROM (
                SELECT wiki_title FROM monitored_titles
                UNION
                SELECT wiki_title FROM watches
            ) x
        """)
        row = _fetchone(cur)
    return row["n"] if row else 0


def get_watch_count_for_title(wiki_title: str) -> int:
    with get_conn() as conn:
        ph = _ph()
        cur = _exec(conn, f"SELECT COUNT(DISTINCT email) AS n FROM watches WHERE wiki_title={ph}", (wiki_title,))
        row = _fetchone(cur)
    return row["n"] if row else 0


def get_watch_counts() -> dict:
    """Batch version of get_watch_count_for_title. One query for all titles
    instead of one query per title (avoids N+1 on /lists/most-monitored)."""
    with get_conn() as conn:
        cur = _exec(conn, """
            SELECT wiki_title, COUNT(DISTINCT email) AS n
            FROM watches
            GROUP BY wiki_title
        """)
        rows = _fetchall(cur)
    return {r["wiki_title"]: r["n"] for r in rows}


def record_death(wiki_title: str, display_name: str, death_date: str, edit_url: str = None) -> bool:
    wiki_url = f"https://en.wikipedia.org/wiki/{wiki_title}"
    with get_conn() as conn:
        if USE_POSTGRES:
            cur = _exec(conn, """
                INSERT INTO deaths (wiki_title, display_name, death_date, detected_at, wiki_url, edit_url)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (wiki_title) DO NOTHING
                RETURNING id
            """, (wiki_title, display_name, death_date, utcnow(), wiki_url, edit_url))
            return _fetchone(cur) is not None
        else:
            cur = _exec(conn, """
                INSERT OR IGNORE INTO deaths (wiki_title, display_name, death_date, detected_at, wiki_url, edit_url)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (wiki_title, display_name, death_date, utcnow(), wiki_url, edit_url))
            return cur.rowcount > 0


def is_already_dead(wiki_title: str) -> bool:
    return get_death_for_title(wiki_title) is not None


def get_death_for_title(wiki_title: str) -> dict | None:
    with get_conn() as conn:
        ph = _ph()
        cur = _exec(conn, f"SELECT * FROM deaths WHERE wiki_title={ph}", (wiki_title,))
        return _fetchone(cur)


def get_deaths(limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        ph = _ph()
        cur = _exec(conn,
            f"SELECT * FROM deaths ORDER BY detected_at DESC LIMIT {ph}",
            (limit,)
        )
        return _fetchall(cur)


def get_death_count() -> int:
    with get_conn() as conn:
        cur = _exec(conn, "SELECT COUNT(*) AS n FROM deaths")
        row = _fetchone(cur)
    return row["n"] if row else 0


# ── Watcher healthcheck ──────────────────────────────────────────────────────
# Single-row healthcheck (key="watcher") so /status can report whether the
# GitHub Actions watcher job is alive and progressing, or silently stuck.

def record_watcher_start() -> None:
    now = utcnow()
    with get_conn() as conn:
        ph = _ph()
        _exec(conn, f"""
            INSERT INTO watcher_health (key, started_at, heartbeat_at, updated_at)
            VALUES ('watcher', {ph}, {ph}, {ph})
            ON CONFLICT (key) DO UPDATE SET
                started_at = excluded.started_at,
                heartbeat_at = excluded.heartbeat_at,
                updated_at = excluded.updated_at
        """, (now, now, now))


def record_watcher_heartbeat() -> None:
    now = utcnow()
    with get_conn() as conn:
        ph = _ph()
        _exec(conn, f"""
            INSERT INTO watcher_health (key, heartbeat_at, updated_at)
            VALUES ('watcher', {ph}, {ph})
            ON CONFLICT (key) DO UPDATE SET
                heartbeat_at = excluded.heartbeat_at,
                updated_at = excluded.updated_at
        """, (now, now))


def record_watcher_event(title: str) -> None:
    now = utcnow()
    safe_title = (title or "")[:200]
    with get_conn() as conn:
        ph = _ph()
        _exec(conn, f"""
            INSERT INTO watcher_health (key, last_event_at, last_checked_title, heartbeat_at, updated_at)
            VALUES ('watcher', {ph}, {ph}, {ph}, {ph})
            ON CONFLICT (key) DO UPDATE SET
                last_event_at = excluded.last_event_at,
                last_checked_title = excluded.last_checked_title,
                heartbeat_at = excluded.heartbeat_at,
                updated_at = excluded.updated_at
        """, (now, safe_title, now, now))


def record_watcher_error(error: str) -> None:
    # Truncate defensively so a runaway exception message can't bloat the row.
    # Caller is responsible for not passing secrets into `error`; this function
    # only does length limiting, not redaction.
    now = utcnow()
    safe_error = (str(error) if error else "")[:500]
    with get_conn() as conn:
        ph = _ph()
        _exec(conn, f"""
            INSERT INTO watcher_health (key, last_error, updated_at)
            VALUES ('watcher', {ph}, {ph})
            ON CONFLICT (key) DO UPDATE SET
                last_error = excluded.last_error,
                updated_at = excluded.updated_at
        """, (safe_error, now))


def get_watcher_health() -> dict | None:
    with get_conn() as conn:
        ph = _ph()
        cur = _exec(conn, f"SELECT * FROM watcher_health WHERE key={ph}", ("watcher",))
        return _fetchone(cur)
