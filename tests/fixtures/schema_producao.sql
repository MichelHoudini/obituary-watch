-- Legacy production schema (origin/master, before migration PRs).
-- Used by MIG-002 to verify migrate_schema() upgrades a real production DB.

CREATE TABLE watches (
    id         SERIAL PRIMARY KEY,
    wiki_title TEXT NOT NULL,
    email      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(wiki_title, email)
);

CREATE TABLE monitored_titles (
    id           SERIAL PRIMARY KEY,
    wiki_title   TEXT UNIQUE NOT NULL,
    display_name TEXT,
    category     TEXT,
    birth_year   INTEGER,
    created_at   TEXT NOT NULL
);

CREATE TABLE deaths (
    id           SERIAL PRIMARY KEY,
    wiki_title   TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    death_date   TEXT,
    detected_at  TEXT NOT NULL,
    wiki_url     TEXT NOT NULL,
    edit_url     TEXT
);

CREATE TABLE watcher_health (
    key                TEXT PRIMARY KEY,
    started_at         TEXT,
    heartbeat_at       TEXT,
    last_event_at      TEXT,
    last_checked_title TEXT,
    last_error         TEXT,
    updated_at         TEXT
);
