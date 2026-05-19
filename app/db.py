"""
db.py — Database layer using PostgreSQL (Supabase).
Falls back to SQLite for local development if DATABASE_URL is not set.
"""

import os
import logging
from datetime import datetime, timezone
from contextlib import contextmanager

log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES  = bool(DATABASE_URL)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


# ── Connection ────────────────────────────────────────────────────────────────

@contextmanager
def get_conn():
    if USE_POSTGRES:
        import psycopg2
        import psycopg2.extras
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
    """Normalize rows from both psycopg2 (tuple) and sqlite3 (Row)."""
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


# ── Schema ────────────────────────────────────────────────────────────────────

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
        else:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS watches (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    wiki_title  TEXT NOT NULL,
                    email       TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    UNIQUE(wiki_title, email)
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
            """)


# ── Watches ───────────────────────────────────────────────────────────────────

def add_watch(wiki_title: str, email: str) -> bool:
    with get_conn() as conn:
        try:
            _exec(conn,
                "INSERT INTO watches (wiki_title, email, created_at) VALUES (%s, %s, %s)"
                if USE_POSTGRES else
                "INSERT INTO watches (wiki_title, email, created_at) VALUES (?,?,?)",
                (wiki_title, email, utcnow())
            )
            return True
        except Exception:
            return False


def get_emails_for(wiki_title: str) -> list[str]:
    with get_conn() as conn:
        ph = "%s" if USE_POSTGRES else "?"
        cur = _exec(conn, f"SELECT email FROM watches WHERE wiki_title={ph}", (wiki_title,))
        rows = _fetchall(cur)
    return [r["email"] for r in rows]


def get_all_watched_titles() -> set[str]:
    with get_conn() as conn:
        cur = _exec(conn, "SELECT DISTINCT wiki_title FROM watches")
        rows = _fetchall(cur)
    return {r["wiki_title"] for r in rows}


# ── Deaths ────────────────────────────────────────────────────────────────────

def record_death(wiki_title: str, display_name: str, death_date: str, edit_url: str = None) -> bool:
    wiki_url = f"https://en.wikipedia.org/wiki/{wiki_title}"
    with get_conn() as conn:
        try:
            if USE_POSTGRES:
                _exec(conn,
                    """INSERT INTO deaths (wiki_title, display_name, death_date, detected_at, wiki_url, edit_url)
                       VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (wiki_title) DO NOTHING""",
                    (wiki_title, display_name, death_date, utcnow(), wiki_url, edit_url)
                )
            else:
                _exec(conn,
                    """INSERT OR IGNORE INTO deaths (wiki_title, display_name, death_date, detected_at, wiki_url, edit_url)
                       VALUES (?,?,?,?,?,?)""",
                    (wiki_title, display_name, death_date, utcnow(), wiki_url, edit_url)
                )
            return True
        except Exception:
            return False


def is_already_dead(wiki_title: str) -> bool:
    with get_conn() as conn:
        ph = "%s" if USE_POSTGRES else "?"
        cur = _exec(conn, f"SELECT 1 FROM deaths WHERE wiki_title={ph}", (wiki_title,))
        return _fetchone(cur) is not None
