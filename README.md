# ObituaryWatch 🕯️

Zero-cost Wikipedia death monitor. Uses Wikipedia's RecentChanges stream (free, event-driven)
and serves an RSS feed (no email infra needed).

## Architecture — cost: $0/month

```
Wikipedia RecentChanges SSE stream
        │
        ▼
   watcher.py  ←── filters edits for watched articles only
        │
        ▼ (death_date detected in infobox)
   SQLite DB  ──→  FastAPI  ──→  RSS feed  ──→  User's RSS reader
```

- **No polling loops** — Wikipedia pushes edit events to us via SSE
- **No email service** — RSS feed is read by any free RSS reader (Feedly, NewsBlur, etc.)
- **SQLite** — zero-config, file-based, free forever
- **FastAPI** — deploy free on Render.com or Railway.app

## Setup

```bash
pip install -r requirements.txt
python -m app.seed          # add some initial people to watch
python -m app.watcher       # start the RecentChanges listener (keep running)
uvicorn app.main:app --reload  # start the API + RSS feed
```

## Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Web UI — manage watchlist |
| `GET /rss` | RSS feed of detected deaths |
| `GET /rss/{list_name}` | RSS feed for a named list |
| `POST /watch` | Add a person/category to watchlist |
| `DELETE /watch/{title}` | Remove from watchlist |
| `GET /deaths` | JSON list of detected deaths |
| `GET /status` | Watcher health + stats |

## Deploy free on Render.com

1. Push to GitHub
2. New Web Service → connect repo
3. Build: `pip install -r requirements.txt`
4. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add a Background Worker for `python -m app.watcher`

Both services are free tier on Render.
