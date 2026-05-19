"""
main.py — FastAPI application.
CSS and JS served as static files — no f-string escaping issues.
"""

import os, base64, json, pathlib
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.db import (
    init_db, add_watched, remove_watched,
    get_all_watched, get_deaths, create_list,
    add_to_list, get_watched_titles,
)
from app.rss import build_global_feed, build_list_feed
from app.wiki import search_person, resolve_title, get_category_people, CATEGORY_QCODES

app = FastAPI(title="ObituaryWatch", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

CATEGORY_ICONS = {
    "actors": "&#127916;", "musicians": "&#127925;", "athletes": "&#9917;",
    "politicians": "&#127963;", "authors": "&#128218;", "directors": "&#127909;",
    "scientists": "&#128300;", "artists": "&#127912;",
}

LOGO_B64 = ""
try:
    with open(os.path.join(STATIC_DIR, "logo.png"), "rb") as f:
        LOGO_B64 = base64.b64encode(f.read()).decode()
except Exception:
    pass

def get_logo_img(size=132):
    # Serve logo directly from static file — simpler and faster than base64
    return f'<img src="/static/logo.png" alt="ObituaryWatch" class="logo-img" style="width:{size}px;height:{size}px">'

def head(title="ObituaryWatch"):
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link href="https://fonts.googleapis.com/css2?family=Special+Elite&family=Courier+Prime:wght@300;400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/style.css">
</head><body>"""

@app.on_event("startup")
def startup():
    init_db()

def base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")

# ── RSS ───────────────────────────────────────────────────────────────────────

@app.get("/rss", response_class=Response)
def global_rss_feed(request: Request):
    return Response(content=build_global_feed(base_url(request)), media_type="application/atom+xml")

@app.get("/rss/{list_slug}", response_class=Response)
def list_rss_feed(list_slug: str, request: Request):
    feed = build_list_feed(list_slug, base_url(request))
    if feed is None:
        raise HTTPException(404, f"List {list_slug!r} not found")
    return Response(content=feed, media_type="application/atom+xml")

# ── API ───────────────────────────────────────────────────────────────────────

class WatchRequest(BaseModel):
    wiki_title: str | None = None
    display_name: str | None = None
    category: str | None = None
    birth_year: int | None = None
    list_slug: str | None = None

class CategoryRequest(BaseModel):
    category: str
    list_slug: str | None = None
    limit: int = 100

class EmailRequest(BaseModel):
    email: str

@app.post("/watch")
def add_watch(req: WatchRequest):
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
    return {"added": is_new, "wiki_title": title, "display_name": name,
            "message": "Added" if is_new else "Already watching"}

@app.post("/watch/category")
def add_category(req: CategoryRequest):
    if req.category.lower() not in CATEGORY_QCODES:
        raise HTTPException(400, "Unknown category.")
    people = get_category_people(req.category, limit=req.limit)
    if not people:
        raise HTTPException(503, "Wikidata returned no results.")
    if req.list_slug:
        create_list(req.list_slug, req.category)
    added = 0
    for p in people:
        if add_watched(p["wiki_title"], p["display_name"], category=req.category):
            added += 1
            if req.list_slug:
                add_to_list(req.list_slug, p["wiki_title"])
    return {"category": req.category, "total_found": len(people), "newly_added": added}

@app.delete("/watch/{wiki_title:path}")
def remove_watch(wiki_title: str):
    remove_watched(wiki_title)
    return {"removed": wiki_title}

@app.get("/watched")
def list_watched():
    return [dict(r) for r in get_all_watched()]

@app.get("/deaths")
def list_deaths(limit: int = 50):
    return [dict(r) for r in get_deaths(limit)]

@app.get("/search")
def search(q: str, limit: int = 6):
    results = search_person(q, limit)
    for r in results:
        if not r.get("description"):
            r["description"] = ""
    return results

@app.get("/categories")
def list_categories():
    return list(CATEGORY_QCODES.keys())

@app.post("/subscribe")
def subscribe(req: EmailRequest):
    emails_path = pathlib.Path(__file__).parent / "subscribers.json"
    try:
        emails = json.loads(emails_path.read_text()) if emails_path.exists() else []
    except Exception:
        emails = []
    if req.email not in emails:
        emails.append(req.email)
        emails_path.write_text(json.dumps(emails, indent=2))
    return {"subscribed": True, "email": req.email}

# ── Watchlist page ────────────────────────────────────────────────────────────

@app.get("/watchlist", response_class=HTMLResponse)
def watchlist_page(request: Request):
    rss_url = f"{base_url(request)}/rss"
    watched = get_all_watched()
    deaths  = get_deaths(limit=50)

    pills = "".join(
        f'<div class="pill">'
        f'<span class="pill-name">{r["display_name"]}</span>'
        f'<span class="pill-cat">{r["category"] or ""}</span>'
        f'<button class="pill-x" data-title="{r["wiki_title"].replace(chr(34), "")}" onclick="removeWatch(this)">&times;</button>'
        f'</div>'
        for r in watched
    ) or '<div class="empty-state">nothing being watched yet — <a href="/">go add some</a></div>'

    death_rows = "".join(
        f'<div class="death-row">'
        f'<a class="death-name" href="{r["wiki_url"]}" target="_blank">{r["display_name"]}</a>'
        f'<span class="death-date">{r["death_date"] or "?"}</span>'
        f'<span class="death-det">{r["detected_at"][:10]}</span>'
        f'</div>'
        for r in deaths
    ) or '<p class="empty-state">none detected yet.</p>'

    return HTMLResponse(head("ObituaryWatch — Watchlist") + f"""
<div class="page">
  <a class="back-link" href="/">&#8592; back</a>
  <div class="header" style="margin-bottom:50px">
    {get_logo_img()}
    <div class="site-name">ObituaryWatch</div>
  </div>
  <div class="rss-bar">
    <span style="color:#c8b89a">&#x25C6;</span>
    <span>RSS: <a href="{rss_url}">{rss_url}</a></span>
  </div>
  <div class="section">
    <div class="section-label">Watchlist &mdash; {len(watched)} people</div>
    <div class="pills-grid">{pills}</div>
  </div>
  <div class="section">
    <div class="section-label">Detected deaths &mdash; {len(deaths)}</div>
    <div>{death_rows}</div>
  </div>
</div>
<script>
async function removeWatch(btn) {{
  await fetch('/watch/' + encodeURIComponent(btn.getAttribute('data-title')), {{method:'DELETE'}});
  btn.closest('.pill').remove();
}}
</script>
</body></html>""")

# ── Main page ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    cat_cards = "".join(
        f'<button class="cat-card" data-cat="{c}" onclick="selectCategory(this)">'
        f'<span class="cat-icon">{CATEGORY_ICONS.get(c, "&#9670;")}</span>'
        f'<span class="cat-label">{c.title()}</span>'
        f'</button>'
        for c in CATEGORY_QCODES
    )

    return HTMLResponse(head() + f"""
<div class="page">

  <div class="header">
    {get_logo_img()}
    <div class="site-name">ObituaryWatch</div>
    <div class="site-tagline">know before everyone else</div>
  </div>

  <div class="section">
    <div class="section-label">Search a person</div>
    <div class="search-wrap" id="search-wrap">
      <input class="search-input" id="search-input" type="text"
        placeholder="type a name... e.g. Nicolas Cage"
        autocomplete="off" spellcheck="false"
        oninput="handleSearch(this.value)"
        onkeydown="handleKey(event)">
      <div class="search-spinner" id="search-spinner"></div>
      <div class="search-results" id="search-results"></div>
    </div>
  </div>

  <div class="section">
    <button class="cat-toggle" id="cat-toggle" onclick="toggleCats()">
      <span class="cat-toggle-arrow">&#9658;</span>
      Browse by category
    </button>
    <div class="cat-section" id="cat-section">
      <div class="cat-grid">{cat_cards}</div>
      <div class="cat-msg" id="cat-msg"></div>
    </div>
  </div>

  <div class="section" id="watchlist-section" style="display:none">
    <div class="section-label">Your watchlist</div>
    <div class="watchlist-preview" id="watchlist-preview"></div>
    <a class="view-all-link" href="/watchlist">view all &amp; detected deaths &#8594;</a>
  </div>

  <div class="section">
    <div class="section-label">Get notified by email</div>
    <div class="email-row">
      <input class="email-input" id="email-input" type="email" placeholder="your@email.com">
      <button class="btn-subscribe" onclick="subscribe()">notify me</button>
    </div>
    <div class="email-msg" id="email-msg"></div>
  </div>

</div>
<script src="/static/app.js"></script>
</body></html>""")
