"""
main.py — FastAPI application.
Serves the management API and RSS feeds.
"""

import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.db import (
    init_db, add_watched, remove_watched,
    get_all_watched, get_deaths, create_list,
    add_to_list, get_watched_titles,
)
from app.rss import build_global_feed, build_list_feed
from app.wiki import search_person, resolve_title, get_category_people, CATEGORY_QCODES

app = FastAPI(title="ObituaryWatch", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


def base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


# ── RSS feeds (the zero-cost notification system) ─────────────────────────────

@app.get("/rss", response_class=Response)
def global_rss_feed(request: Request):
    """
    Atom feed of ALL detected deaths.
    Subscribe to this URL in any RSS reader.
    """
    feed = build_global_feed(base_url(request))
    return Response(content=feed, media_type="application/atom+xml")


@app.get("/rss/{list_slug}", response_class=Response)
def list_rss_feed(list_slug: str, request: Request):
    """
    Atom feed scoped to a named watchlist.
    E.g. /rss/my-musicians only shows deaths of people in that list.
    """
    feed = build_list_feed(list_slug, base_url(request))
    if feed is None:
        raise HTTPException(status_code=404, detail=f"List {list_slug!r} not found")
    return Response(content=feed, media_type="application/atom+xml")


# ── Watchlist management ──────────────────────────────────────────────────────

class WatchRequest(BaseModel):
    wiki_title: str | None = None    # exact Wikipedia title (underscore form)
    display_name: str | None = None  # if omitted, resolved from wiki_title
    category: str | None = None
    birth_year: int | None = None
    list_slug: str | None = None     # optionally add to a named list


class CategoryRequest(BaseModel):
    category: str        # e.g. "actors", "musicians"
    list_slug: str | None = None
    limit: int = 100     # how many people to add from this category


@app.post("/watch")
def add_watch(req: WatchRequest):
    """Add a single person to the watchlist."""
    title = req.wiki_title
    name  = req.display_name

    if not title and not name:
        raise HTTPException(400, "Provide wiki_title or display_name")

    if not title:
        title = resolve_title(name)
        if not title:
            raise HTTPException(404, f"Could not find Wikipedia article for {name!r}")

    if not name:
        name = title.replace("_", " ")

    is_new = add_watched(title, name, req.category, req.birth_year)

    if req.list_slug:
        create_list(req.list_slug, req.list_slug)
        add_to_list(req.list_slug, title)

    return {
        "added": is_new,
        "wiki_title": title,
        "display_name": name,
        "message": "Added" if is_new else "Already watching",
    }


@app.post("/watch/category")
def add_category(req: CategoryRequest):
    """
    Add all living people in a Wikidata category to the watchlist.
    Uses Wikidata SPARQL — one request, then done. No polling.
    """
    if req.category.lower() not in CATEGORY_QCODES:
        raise HTTPException(400, f"Unknown category. Options: {list(CATEGORY_QCODES.keys())}")

    people = get_category_people(req.category, limit=req.limit)
    if not people:
        raise HTTPException(503, "Wikidata SPARQL returned no results. Try again.")

    if req.list_slug:
        create_list(req.list_slug, req.category)

    added = 0
    for p in people:
        is_new = add_watched(p["wiki_title"], p["display_name"], category=req.category)
        if is_new:
            added += 1
            if req.list_slug:
                add_to_list(req.list_slug, p["wiki_title"])

    return {
        "category": req.category,
        "total_found": len(people),
        "newly_added": added,
        "already_watching": len(people) - added,
        "list_slug": req.list_slug,
    }


@app.delete("/watch/{wiki_title:path}")
def remove_watch(wiki_title: str):
    remove_watched(wiki_title)
    return {"removed": wiki_title}


@app.get("/watched")
def list_watched():
    rows = get_all_watched()
    return [dict(r) for r in rows]


# ── Deaths & search ───────────────────────────────────────────────────────────

@app.get("/deaths")
def list_deaths(limit: int = 50):
    return [dict(r) for r in get_deaths(limit)]


@app.get("/search")
def search(q: str, limit: int = 8):
    """Search Wikipedia for people matching query. Used by the frontend."""
    return search_person(q, limit)


@app.get("/status")
def status(request: Request):
    watched = get_watched_titles()
    deaths  = get_deaths(limit=1)
    rss_url = f"{base_url(request)}/rss"
    return {
        "watching": len(watched),
        "deaths_detected": len(get_deaths(limit=9999)),
        "rss_feed": rss_url,
        "tip": f"Subscribe to {rss_url} in your RSS reader (Feedly, NewsBlur, etc.)",
    }


@app.get("/categories")
def list_categories():
    return list(CATEGORY_QCODES.keys())


# ── Minimal web UI ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    rss_url = f"{base_url(request)}/rss"
    watched = get_all_watched()
    deaths  = get_deaths(limit=20)

    watched_rows = "".join(
        f"<tr><td>{r['display_name']}</td><td>{r['category'] or '—'}</td>"
        f"<td>{r['last_checked'] or 'pending'}</td>"
        f"<td><button onclick=\"removeWatch('{r['wiki_title']}')\">✕</button></td></tr>"
        for r in watched
    )
    death_rows = "".join(
        f"<tr><td><a href='{r['wiki_url']}' target='_blank'>{r['display_name']}</a></td>"
        f"<td>{r['death_date'] or '?'}</td><td>{r['detected_at'][:10]}</td></tr>"
        for r in deaths
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ObituaryWatch</title>
<style>
  body {{ font-family: system-ui; max-width: 860px; margin: 40px auto; padding: 0 20px; color: #222; }}
  h1 {{ font-size: 1.4rem; }} h2 {{ font-size: 1rem; margin-top: 2rem; border-bottom: 1px solid #eee; padding-bottom: 6px; }}
  .rss-box {{ background: #fff8e1; border: 1px solid #f0c040; border-radius: 6px; padding: 12px 16px; margin: 16px 0; }}
  .rss-box a {{ color: #b45309; font-weight: 500; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th {{ text-align: left; color: #666; font-weight: 500; padding: 6px 8px; border-bottom: 1px solid #eee; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #f5f5f5; }}
  input, select {{ padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }}
  button {{ padding: 6px 14px; background: #4B1528; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }}
  button:hover {{ background: #72243E; }}
  .form-row {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; background: #fee2e2; color: #7f1d1d; }}
</style>
</head>
<body>
<h1>🕯️ ObituaryWatch</h1>
<p>Zero-cost Wikipedia death monitor. Uses the Wikipedia RecentChanges stream — no polling, no email service.</p>

<div class="rss-box">
  📡 <strong>Your RSS feed:</strong> <a href="{rss_url}">{rss_url}</a><br>
  <small>Subscribe to this URL in Feedly, NewsBlur, NetNewsWire, or any RSS reader. Free forever.</small>
</div>

<h2>Add person</h2>
<div class="form-row">
  <input id="name" placeholder="e.g. Paul McCartney" style="flex:1;min-width:200px">
  <select id="cat">
    <option value="">— category —</option>
    {"".join(f'<option value="{c}">{c.title()}</option>' for c in CATEGORY_QCODES)}
  </select>
  <button onclick="addPerson()">Watch</button>
</div>

<h2>Add entire category</h2>
<div class="form-row">
  <select id="bulk-cat">
    {"".join(f'<option value="{c}">{c.title()}</option>' for c in CATEGORY_QCODES)}
  </select>
  <input id="bulk-list" placeholder="list name (optional)" style="width:160px">
  <button onclick="addCategory()">Add all living people in category</button>
</div>
<p id="bulk-msg" style="font-size:13px;color:#666"></p>

<h2>Watchlist ({len(watched)} people)</h2>
<table>
  <thead><tr><th>Name</th><th>Category</th><th>Last checked</th><th></th></tr></thead>
  <tbody id="watch-tbody">{watched_rows}</tbody>
</table>

<h2>Detected deaths ({len(deaths)})</h2>
{"<p style='color:#666;font-size:14px'>None yet.</p>" if not deaths else f'''
<table>
  <thead><tr><th>Name</th><th>Death date</th><th>Detected</th></tr></thead>
  <tbody>{death_rows}</tbody>
</table>'''}

<script>
async function addPerson() {{
  const name = document.getElementById('name').value.trim();
  const cat  = document.getElementById('cat').value;
  if (!name) return alert('Enter a name');
  const r = await fetch('/watch', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ display_name: name, category: cat || null }})
  }});
  const d = await r.json();
  alert(d.message + ': ' + d.display_name);
  location.reload();
}}

async function addCategory() {{
  const cat  = document.getElementById('bulk-cat').value;
  const slug = document.getElementById('bulk-list').value.trim() || null;
  document.getElementById('bulk-msg').textContent = 'Querying Wikidata… this takes ~10s';
  const r = await fetch('/watch/category', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ category: cat, list_slug: slug, limit: 200 }})
  }});
  const d = await r.json();
  document.getElementById('bulk-msg').textContent =
    `Added ${{d.newly_added}} people (${{d.already_watching}} already watched).`;
  location.reload();
}}

async function removeWatch(title) {{
  await fetch('/watch/' + encodeURIComponent(title), {{ method: 'DELETE' }});
  location.reload();
}}
</script>
</body>
</html>"""
