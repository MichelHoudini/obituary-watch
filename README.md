# Mortivox 🕯️

Wikipedia death monitor and public watch-page directory.

Mortivox watches selected Wikipedia pages through Wikimedia's live RecentChanges
stream, records death-related changes, exposes a public detection log, and lets
users subscribe to email notifications for specific profiles.

## Architecture

```text
Wikimedia RecentChanges SSE stream
        │
        ▼
   app/watcher.py  ── filters edits for monitored Wikipedia titles
        │
        ▼
   PostgreSQL / SQLite
        │
        ├── FastAPI public site
        ├── public person pages
        ├── deaths log
        ├── Atom RSS feed
        └── email notifications via Resend
```

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
| `GET /status` | Health/status payload |
| `POST /watch` | Subscribe an email to a Wikipedia page |

## Local setup

```bash
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload
```

Run the watcher separately:

```bash
python -m app.watcher
```

If `DATABASE_URL` is set, Mortivox uses PostgreSQL. Otherwise it falls back to a
local SQLite file named `obituary_watch.db`.

## Render deploy

Web service:

```bash
Build: pip install -r requirements.txt
Start: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Background worker:

```bash
python -m app.watcher
```

Environment variables:

```text
DATABASE_URL
RESEND_API_KEY
```

`app.main` seeds the curated catalog on startup into `monitored_titles`, so public
watch pages exist even before individual users subscribe.
