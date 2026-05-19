"""
db.py — Minimal database. Just two tables.
watches: who is watching what email
deaths:  confirmed deaths detected from Wikipedia
"""

import sqlite3
import os
from datetime import datetime, timezone
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "obituary_watch.db")


def utcnow():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
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


def init_db():
    with get_conn() as conn:
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


def add_watch(wiki_title: str, email: str) -> bool:
    """Returns True if newly added."""
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO watches (wiki_title, email, created_at) VALUES (?,?,?)",
                (wiki_title, email, utcnow())
            )
            return True
        except sqlite3.IntegrityError:
            return False


def get_emails_for(wiki_title: str) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT email FROM watches WHERE wiki_title=?", (wiki_title,)
        ).fetchall()
    return [r["email"] for r in rows]


def get_all_watched_titles() -> set[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT wiki_title FROM watches").fetchall()
    return {r["wiki_title"] for r in rows}


def record_death(wiki_title: str, display_name: str, death_date: str, edit_url: str = None) -> bool:
    wiki_url = f"https://en.wikipedia.org/wiki/{wiki_title}"
    with get_conn() as conn:
        try:
            conn.execute(
                """INSERT INTO deaths (wiki_title, display_name, death_date, detected_at, wiki_url, edit_url)
                   VALUES (?,?,?,?,?,?)""",
                (wiki_title, display_name, death_date, utcnow(), wiki_url, edit_url)
            )
            return True
        except sqlite3.IntegrityError:
            return False


def is_already_dead(wiki_title: str) -> bool:
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM deaths WHERE wiki_title=?", (wiki_title,)
        ).fetchone() is not None
