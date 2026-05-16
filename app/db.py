"""
db.py — SQLite database layer. Zero config, zero cost.

Tables:
  watched      — articles/categories we're monitoring
  deaths       — confirmed death detections
  lists        — named watchlists (e.g. "my-actors")
  list_members — many-to-many: lists <-> watched
"""

import sqlite3
import os
from datetime import datetime, timezone
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "obituary_watch.db")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # safe for concurrent reads + one writer
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS watched (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                wiki_title  TEXT UNIQUE NOT NULL,   -- exact Wikipedia article title, e.g. "Paul_McCartney"
                display_name TEXT NOT NULL,          -- human-readable name
                category    TEXT,                    -- "Musician", "Actor", etc. — optional
                birth_year  INTEGER,
                added_at    TEXT NOT NULL,
                last_checked TEXT,
                is_active   INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS deaths (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                wiki_title   TEXT NOT NULL,
                display_name TEXT NOT NULL,
                death_date   TEXT,                   -- raw value from Wikipedia infobox
                detected_at  TEXT NOT NULL,
                wiki_url     TEXT NOT NULL,
                edit_url     TEXT,                   -- diff URL of the edit that added death_date
                UNIQUE(wiki_title)                   -- one entry per person, no dupes
            );

            CREATE TABLE IF NOT EXISTS lists (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                slug       TEXT UNIQUE NOT NULL,     -- URL-safe name, e.g. "my-musicians"
                label      TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS list_members (
                list_id  INTEGER REFERENCES lists(id) ON DELETE CASCADE,
                watch_id INTEGER REFERENCES watched(id) ON DELETE CASCADE,
                PRIMARY KEY (list_id, watch_id)
            );
        """)


# ── Watched articles ──────────────────────────────────────────────────────────

def add_watched(wiki_title: str, display_name: str, category: str = None, birth_year: int = None) -> bool:
    """Returns True if newly added, False if already existed."""
    with get_conn() as conn:
        try:
            conn.execute(
                """INSERT INTO watched (wiki_title, display_name, category, birth_year, added_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (wiki_title, display_name, category, birth_year, utcnow()),
            )
            return True
        except sqlite3.IntegrityError:
            return False  # already watching


def remove_watched(wiki_title: str):
    with get_conn() as conn:
        conn.execute("UPDATE watched SET is_active=0 WHERE wiki_title=?", (wiki_title,))


def get_all_watched() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM watched WHERE is_active=1 ORDER BY display_name"
        ).fetchall()


def get_watched_titles() -> set[str]:
    """Fast lookup set used by the watcher hot path."""
    with get_conn() as conn:
        rows = conn.execute("SELECT wiki_title FROM watched WHERE is_active=1").fetchall()
    return {r["wiki_title"] for r in rows}


def mark_checked(wiki_title: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE watched SET last_checked=? WHERE wiki_title=?",
            (utcnow(), wiki_title),
        )


# ── Deaths ────────────────────────────────────────────────────────────────────

def record_death(wiki_title: str, display_name: str, death_date: str, edit_url: str = None) -> bool:
    """Returns True if this is a new death (not a duplicate)."""
    wiki_url = f"https://en.wikipedia.org/wiki/{wiki_title}"
    with get_conn() as conn:
        try:
            conn.execute(
                """INSERT INTO deaths (wiki_title, display_name, death_date, detected_at, wiki_url, edit_url)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (wiki_title, display_name, death_date, utcnow(), wiki_url, edit_url),
            )
            return True
        except sqlite3.IntegrityError:
            return False  # already recorded


def get_deaths(limit: int = 50) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM deaths ORDER BY detected_at DESC LIMIT ?", (limit,)
        ).fetchall()


def is_already_dead(wiki_title: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM deaths WHERE wiki_title=?", (wiki_title,)
        ).fetchone()
    return row is not None


# ── Lists ─────────────────────────────────────────────────────────────────────

def create_list(slug: str, label: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO lists (slug, label, created_at) VALUES (?,?,?)",
            (slug, label, utcnow()),
        )
        if cur.lastrowid:
            return cur.lastrowid
        return conn.execute("SELECT id FROM lists WHERE slug=?", (slug,)).fetchone()["id"]


def add_to_list(list_slug: str, wiki_title: str):
    with get_conn() as conn:
        list_id = conn.execute("SELECT id FROM lists WHERE slug=?", (list_slug,)).fetchone()
        watch_id = conn.execute("SELECT id FROM watched WHERE wiki_title=?", (wiki_title,)).fetchone()
        if list_id and watch_id:
            conn.execute(
                "INSERT OR IGNORE INTO list_members VALUES (?,?)",
                (list_id["id"], watch_id["id"]),
            )


def get_list_deaths(list_slug: str) -> list[sqlite3.Row]:
    """Deaths for people in a specific named list."""
    with get_conn() as conn:
        return conn.execute(
            """SELECT d.* FROM deaths d
               JOIN watched w ON w.wiki_title = d.wiki_title
               JOIN list_members lm ON lm.watch_id = w.id
               JOIN lists l ON l.id = lm.list_id
               WHERE l.slug = ?
               ORDER BY d.detected_at DESC""",
            (list_slug,),
        ).fetchall()
