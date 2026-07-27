# Mortivox 🕯️

Paste a Wikipedia link. Get notified when that page records a death.

Mortivox watches selected Wikipedia pages through Wikimedia's live
RecentChanges stream, records death-related infobox changes, exposes a
public detection log, and lets people subscribe to email notifications for
specific profiles.

Live at [mortivox.com](https://mortivox.com).

## Architecture

```text
Wikimedia RecentChanges SSE stream
        │
        ▼
   app/watcher.py  ── filters edits for monitored Wikipedia titles,
        │              validates the death_date field is a real date
        │              (not just Wikipedia's placeholder comment)
        ▼
   PostgreSQL / SQLite
        │
        ├── FastAPI public site (app/main.py)
        │     ├── public person pages
        │     ├── deaths log
        │     ├── Atom RSS feed
        │     └── rate-limited /watch subscription endpoint
        └── email notifications via Resend
```

**The watcher doesn't run as a persistent process.** It's a scheduled
GitHub Actions job (`.github/workflows/watcher.yml`) that connects to the
stream, listens for up to ~48 minutes, then exits — currently every 2 hours.
This trades a small detection-latency gap for running on GitHub's free
Actions minutes instead of paying for an always-on worker.

A separate scheduled job (`.github/workflows/milestones.yml`, Mon/Wed/Fri)
sends a one-off notification when the watch count crosses a milestone
(10/50/100/500/1000/2000/3000 watchers).

## Main routes

| Route | Description |
|---|---|
| `GET /` | Landing page and watch form |
| `GET /people` | Public directory of monitored profiles |
| `GET /person/{slug}` | Public watch page for a profile |
| `GET /deaths` | Human-readable death detection log |
| `GET /api/deaths` | JSON death detection log |
| `GET /rss` | Atom feed of detected deaths |
| `GET /lists/most-monitored` | Most subscribed pages |
| `GET /lists/oldest-living` | Long-lived public figures watchlist |
| `GET /lists/actors` | Actors watchlist |
| `GET /lists/musicians` | Musicians watchlist |
| `GET /sitemap.xml` | SEO sitemap |
| `GET /robots.txt` | Robots policy with sitemap URL |
| `GET /status` | Health/status payload, including watcher heartbeat |
| `POST /watch` | Subscribe an email to a Wikipedia page (rate-limited, 5/min/IP) |

## Local setup

```bash
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload
```

Run the watcher separately (needs `DATABASE_URL` in the environment):

```bash
python -m app.watcher
```

If `DATABASE_URL` is unset, Mortivox falls back to a local SQLite file
named `obituary_watch.db` — no Postgres needed for local development.

## Deploy

**Web service (Render):**

```text
Build:  pip install -r requirements.txt
Start:  uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**Watcher and milestone notifier (GitHub Actions, not Render):**
run on their own schedules directly from `.github/workflows/`, using
repository secrets — no separate worker service needed.

### Environment variables

| Variable | Required | Used by |
|---|---|---|
| `DATABASE_URL` | No (falls back to SQLite) | app, watcher, milestones |
| `RESEND_API_KEY` | Yes, for email sending | app, milestones |
| `ANALYTICS_HEAD_SNIPPET` | No | app (renders nothing if unset — see `docs/analytics.md`) |

`app.main` seeds the curated catalog on startup into `monitored_titles`,
so public watch pages exist even before individual users subscribe. It
also runs a one-time data repair on startup that removes any death record
whose date is just Wikipedia's placeholder comment rather than a real date
(self-limiting: a no-op once there's nothing left to clean up).

## Docs

- [`docs/search-console.md`](docs/search-console.md) — Google Search
  Console setup and indexing checklist
- [`docs/analytics.md`](docs/analytics.md) — how `ANALYTICS_HEAD_SNIPPET`
  works and why it's a raw snippet instead of provider-specific config

## License

[MIT](LICENSE)
