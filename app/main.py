"""
main.py - FastAPI app for Mortivox.
"""

import html
import json
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.catalog import CATALOG, LISTS, catalog_people, find_catalog_person, title_to_slug, get_list_people
from app.db import (
    init_db, add_watch, add_watched, get_all_watched_titles,
    get_deaths, get_watch_count, get_death_count,
    get_watch_count_for_title, get_death_for_title, get_watch_counts,
    get_watcher_health, remove_false_death_detections,
)
from app.email import send_watch_confirmation
from app.wiki import get_person_info
from app.rss import build_global_feed

app = FastAPI(title="Mortivox", version="3.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Analytics (optional, env-var driven) ─────────────────────────────────────
# ANALYTICS_HEAD_SNIPPET holds the exact HTML/JS snippet the analytics
# provider gives you (Plausible, Umami, or anything else), pasted as-is.
# If unset/empty, nothing is rendered and the site behaves exactly as before.
#
# Why a raw snippet instead of provider-specific env vars: analytics
# providers change their embed format over time (e.g. Plausible's Oct 2025
# script update dropped the data-domain attribute and now ships a unique,
# two-tag snippet per site — https://plausible.io/docs/script-update-guide).
# A raw snippet means this code never needs to change again when a provider
# changes its markup; only the env var value does.
#
# This is operator-controlled (set via Render's dashboard/API, not by site
# visitors), so injecting it verbatim into <head> carries the same trust
# level as any other env var (DATABASE_URL, RESEND_API_KEY, etc.) — it is
# not user input and not an XSS vector from the public.
ANALYTICS_HEAD_SNIPPET = os.environ.get("ANALYTICS_HEAD_SNIPPET", "").strip()

# How stale the watcher's last heartbeat can be before /status flags it.
# GitHub Actions runs the watcher hourly, so 2h30 gives room for one missed run.
WATCHER_STALE_HOURS = 2.5


@app.on_event("startup")
def startup():
    init_db()
    seed_catalog_titles()
    removed = remove_false_death_detections()
    if removed:
        print(f"[startup] removed {len(removed)} false death detection(s): {removed}")


def seed_catalog_titles():
    for person in CATALOG:
        add_watched(
            person["wiki_title"],
            person["display_name"],
            person["category"],
            person.get("birth_year"),
        )


def base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def js(value) -> str:
    """Safely embed a Python value as a JS literal inside an inline <script>
    tag. Uses json.dumps (correct for JS, unlike html.escape) and additionally
    escapes '</' so the value can never prematurely close the script tag."""
    return json.dumps(value).replace("</", r"<\/")


def wiki_url(title: str) -> str:
    return f"https://en.wikipedia.org/wiki/{quote(title)}"


def analytics_snippet() -> str:
    """Return the operator-configured analytics snippet verbatim, or nothing
    at all if ANALYTICS_HEAD_SNIPPET is unset. Fails safe: an empty env var
    means no script is rendered (never raises, never breaks the page)."""
    return ANALYTICS_HEAD_SNIPPET


def tracking_script() -> str:
    """Always-present, always-safe event helper.

    window.trackEvent(name, props) no-ops if no analytics provider loaded.
    Only ever pass non-personal fields (wiki_title, slug, page_type,
    category, success) — never email or other personal data."""
    return """
    <script>
      window.trackEvent = function(name, props) {
        try {
          props = props || {};
          if (typeof window.plausible === 'function') { window.plausible(name, {props: props}); return; }
          if (window.umami && typeof window.umami.track === 'function') { window.umami.track(name, props); return; }
        } catch (err) {}
      };
    </script>
    """


CSS = """
:root{--mv-bg:#0a0a0a;--mv-surface:#111;--mv-surface-raised:#1a1a1a;--mv-surface-muted:#0d0d0d;--mv-border:#222;--mv-border-hover:#333;--mv-text-primary:#f0f0f0;--mv-text-secondary:#a0a0a0;--mv-text-tertiary:#707070;--mv-text-quaternary:#505050;--mv-danger:#e74c3c;--mv-danger-glow:rgba(231,76,60,.4);--mv-positive:#2ecc71;--mv-radius-sm:6px;--mv-radius-md:10px;--mv-radius-lg:12px;--mv-transition:150ms ease-out}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--mv-bg);color:var(--mv-text-primary);line-height:1.5;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
.page{min-height:100vh;padding:40px 20px}.container{width:min(980px,100%);margin:0 auto}
.nav{display:flex;align-items:center;justify-content:space-between;margin-bottom:64px;color:var(--mv-text-quaternary);font-size:12px;text-transform:uppercase;letter-spacing:.12em}.nav-links{display:flex;gap:20px;flex-wrap:wrap}.nav a:hover{color:var(--mv-text-secondary)}
.hero{min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:48px 20px;position:relative}.hero::before{content:"";position:absolute;top:0;left:50%;transform:translateX(-50%);width:min(600px,80%);height:1px;background:linear-gradient(90deg,transparent,var(--mv-border),transparent)}
.hero h1,.title{font-size:clamp(36px,8vw,64px);font-weight:500;letter-spacing:-.02em;line-height:1.05;margin-bottom:16px}.tagline,.lede{font-size:16px;color:var(--mv-text-tertiary);max-width:620px;margin:0 auto 40px;line-height:1.6}
.input-group{display:flex;width:100%;max-width:520px;border-radius:var(--mv-radius-md);border:1px solid var(--mv-border);background:var(--mv-surface);overflow:hidden;transition:border-color var(--mv-transition)}.input-group:focus-within{border-color:var(--mv-text-primary)}.input-group input{flex:1;padding:16px 20px;border:none;outline:none;background:transparent;font-size:15px;color:var(--mv-text-primary);font-family:inherit}.input-group input::placeholder{color:var(--mv-text-quaternary)}.input-group button,.button{padding:16px 28px;border:none;outline:none;background:var(--mv-text-primary);color:var(--mv-bg);font-size:14px;font-weight:500;cursor:pointer;white-space:nowrap;display:inline-flex;align-items:center;gap:8px;font-family:inherit;transition:opacity var(--mv-transition);border-radius:var(--mv-radius-md)}.input-group button:hover,.button:hover{opacity:.85}.input-group button:disabled{opacity:.5;cursor:not-allowed}.secondary{background:transparent;color:var(--mv-text-secondary);border:1px solid var(--mv-border)}.hint{margin-top:12px;font-size:12px;color:var(--mv-text-quaternary)}
#step2{display:none;width:100%;max-width:520px;flex-direction:column;align-items:center;gap:12px}#step2.visible{display:flex}.back-btn{font-size:12px;color:var(--mv-text-quaternary);cursor:pointer;background:none;border:none;font-family:inherit;padding:4px 0;transition:color var(--mv-transition)}.back-btn:hover{color:var(--mv-text-secondary)}
.person-card,.alert-card,.panel{display:flex;align-items:center;gap:14px;padding:16px 18px;border-radius:var(--mv-radius-md);border:1px solid var(--mv-border);background:var(--mv-surface);transition:border-color var(--mv-transition),background var(--mv-transition)}.person-card:hover,.alert-card:hover,.panel:hover{border-color:var(--mv-border-hover);background:var(--mv-surface-raised)}
.person-thumb,.avatar{width:48px;height:48px;border-radius:50%;object-fit:cover;border:1px solid var(--mv-border);flex-shrink:0;background:var(--mv-surface-raised)}.person-thumb-placeholder,.avatar-placeholder{width:48px;height:48px;border-radius:50%;border:1px solid var(--mv-border);flex-shrink:0;background:var(--mv-surface-raised);display:flex;align-items:center;justify-content:center;color:var(--mv-text-quaternary);font-size:18px}.person-info,.card-body{flex:1;min-width:0}.pname,.card-title{font-size:15px;font-weight:500;color:var(--mv-text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pdesc,.card-meta{font-size:12px;color:var(--mv-text-quaternary);margin-top:2px}
.success-msg{display:none;flex-direction:column;align-items:center;gap:12px;color:var(--mv-text-secondary);font-size:14px}.success-msg.visible{display:flex}.success-icon{width:44px;height:44px;border-radius:50%;background:color-mix(in srgb,var(--mv-positive) 12%,transparent);border:1px solid color-mix(in srgb,var(--mv-positive) 30%,transparent);display:flex;align-items:center;justify-content:center}.scroll-down{position:absolute;bottom:32px;display:flex;flex-direction:column;align-items:center;gap:6px;color:var(--mv-text-quaternary);font-size:11px;letter-spacing:.05em;animation:float 3s ease-in-out infinite}@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(6px)}}
.section{padding:80px 20px;border-top:1px solid var(--mv-border)}.section-title{text-align:center;font-size:11px;font-weight:500;color:var(--mv-text-quaternary);text-transform:uppercase;letter-spacing:.12em;margin-bottom:48px}.steps{display:flex;flex-direction:column;gap:40px;max-width:720px;margin:0 auto}.step{display:flex;align-items:flex-start;gap:20px}.step-num{width:36px;height:36px;border-radius:var(--mv-radius-sm);border:1px solid var(--mv-border);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:500;color:var(--mv-text-tertiary);flex-shrink:0}.step-body h3{font-size:16px;font-weight:500;margin-bottom:6px}.step-body p{font-size:14px;color:var(--mv-text-tertiary);line-height:1.6}
.stats-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;max-width:720px;margin:0 auto}.stat-card{text-align:center;padding:28px 16px;border-radius:var(--mv-radius-md);border:1px solid var(--mv-border);background:var(--mv-surface)}.stat-card .num{font-size:28px;font-weight:500;font-variant-numeric:tabular-nums;line-height:1.1;margin-bottom:6px}.stat-card .label{font-size:12px;color:var(--mv-text-tertiary)}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}.list-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:32px}.badge{font-size:11px;font-weight:500;padding:4px 10px;border-radius:4px;background:rgba(255,255,255,.04);color:var(--mv-text-tertiary);white-space:nowrap;flex-shrink:0}.badge.danger{background:color-mix(in srgb,var(--mv-danger) 10%,transparent);color:var(--mv-danger)}.badge.ok{background:color-mix(in srgb,var(--mv-positive) 10%,transparent);color:var(--mv-positive)}
.person-hero{display:grid;grid-template-columns:120px 1fr;gap:28px;align-items:center;margin-bottom:36px}.person-hero .avatar,.person-hero .avatar-placeholder{width:120px;height:120px;font-size:40px}.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:28px 0}.kv div{padding:16px;border:1px solid var(--mv-border);border-radius:var(--mv-radius-md);background:var(--mv-surface)}.kv strong{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:var(--mv-text-quaternary);margin-bottom:6px}.kv span{font-size:14px;color:var(--mv-text-secondary)}
.footer{text-align:center;padding:40px 20px;border-top:1px solid var(--mv-border)}.footer p{font-size:12px;color:var(--mv-text-quaternary)}.footer .links{display:flex;justify-content:center;gap:24px;margin-top:16px;flex-wrap:wrap}.footer .links a{font-size:12px;color:var(--mv-text-quaternary);transition:color var(--mv-transition)}.footer .links a:hover{color:var(--mv-text-secondary)}
@media(min-width:640px){.steps{flex-direction:row;gap:48px}.step{flex-direction:column;align-items:center;text-align:center;flex:1}}@media(max-width:640px){.stats-grid{grid-template-columns:1fr}.input-group{flex-direction:column}.input-group button{justify-content:center}.person-hero{grid-template-columns:1fr;text-align:center}.person-hero .avatar,.person-hero .avatar-placeholder{margin:0 auto}.nav{align-items:flex-start;gap:16px;flex-direction:column}}
"""


def layout(request: Request, title: str, description: str, body: str, canonical_path: str = "/", image_path: str = "/skull.png?v=3") -> str:
    site = base_url(request)
    canonical = f"{site}{canonical_path}"
    image_url = f"{site}{image_path}"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{e(title)}</title>
  <meta name="description" content="{e(description)}">
  <link rel="canonical" href="{e(canonical)}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Mortivox">
  <meta property="og:title" content="{e(title)}">
  <meta property="og:description" content="{e(description)}">
  <meta property="og:url" content="{e(canonical)}">
  <meta property="og:image" content="{e(image_url)}">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="{e(title)}">
  <meta name="twitter:description" content="{e(description)}">
  <meta name="twitter:image" content="{e(image_url)}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&display=swap" rel="stylesheet">
  <style>{CSS}</style>
  {analytics_snippet()}
  {tracking_script()}
</head>
<body>{body}</body>
</html>"""


def nav() -> str:
    return """
    <nav class="nav">
      <a href="/">mortivox</a>
      <div class="nav-links">
        <a href="/people">people</a>
        <a href="/deaths">deaths</a>
        <a href="/lists/most-monitored">most monitored</a>
        <a href="/rss">rss</a>
      </div>
    </nav>
    """


def footer() -> str:
    return """
    <footer class="footer">
      <p>mortivox &mdash; silent watch, respectful notification</p>
      <div class="links"><a href="/people">people</a><a href="/deaths">deaths</a><a href="/rss">rss feed</a><a href="/status">status</a></div>
    </footer>
    """


def person_card(person: dict, info: dict | None = None, extra: str = "") -> str:
    title = person["wiki_title"]
    name = person.get("display_name") or title.replace("_", " ")
    slug = person.get("slug") or title_to_slug(title)
    category = person.get("category") or (info or {}).get("occupation") or "Public figure"
    thumb = (info or {}).get("thumbnail")
    image = f'<img class="avatar" src="{e(thumb)}" alt="{e(name)}">' if thumb else f'<div class="avatar-placeholder">{e(name[:1])}</div>'
    return f"""
    <a class="person-card" href="/person/{e(slug)}">
      {image}
      <div class="person-info">
        <div class="pname">{e(name)}</div>
        <div class="pdesc">{e(category)}{extra}</div>
      </div>
      <span class="badge">watch</span>
    </a>
    """


def death_card(row: dict) -> str:
    slug = title_to_slug(row["wiki_title"])
    death_date = row.get("death_date") or "confirmed"
    return f"""
    <a class="alert-card" href="/person/{e(slug)}">
      <div class="alert-dot" style="width:8px;height:8px;border-radius:50%;background:var(--mv-danger);box-shadow:0 0 8px var(--mv-danger-glow);flex-shrink:0"></div>
      <div class="alert-info">
        <div class="name">{e(row["display_name"])}</div>
        <div class="when">detected {e(str(row.get("detected_at", ""))[:10])}</div>
      </div>
      <span class="badge danger">{e(death_date)}</span>
    </a>
    """


@app.get("/rss", response_class=Response)
def global_rss_feed(request: Request):
    feed = build_global_feed(base_url(request))
    return Response(content=feed, media_type="application/atom+xml")


class WatchRequest(BaseModel):
    wiki_title: str
    email: str


@app.post("/watch")
def add_watch_endpoint(req: WatchRequest, request: Request):
    if not req.wiki_title or not req.email:
        raise HTTPException(400, "wiki_title and email are required")
    title = req.wiki_title.strip().replace(" ", "_")
    email = req.email.strip().lower()
    is_new = add_watch(title, email)
    info = get_person_info(title)
    person_name = (info or {}).get("name") or title.replace("_", " ")
    send_watch_confirmation(email, person_name, wiki_url(title))
    return {
        "added": is_new,
        "wiki_title": title,
        "message": "Added" if is_new else "Already watching",
        "person_url": f"{base_url(request)}/person/{title_to_slug(title)}",
    }


@app.get("/api/person")
@app.get("/person")
def person_info(wiki_title: str):
    info = get_person_info(wiki_title)
    if not info:
        raise HTTPException(404, "Person not found")
    return info


@app.get("/api/deaths")
@app.get("/deaths.json")
def list_deaths_api(limit: int = 50):
    return get_deaths(limit)


def _watcher_is_stale(health: dict | None) -> bool:
    """True if the watcher has never reported in, or its last heartbeat is
    older than WATCHER_STALE_HOURS. GitHub Actions runs the watcher hourly,
    so this tolerates one missed run before flagging a problem."""
    if not health or not health.get("heartbeat_at"):
        return True
    try:
        heartbeat = datetime.fromisoformat(health["heartbeat_at"])
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - heartbeat
        return age > timedelta(hours=WATCHER_STALE_HOURS)
    except Exception:
        # Malformed timestamp is treated as stale rather than raising —
        # /status must never 500 because of a healthcheck row.
        return True


@app.get("/status")
def status(request: Request):
    health = get_watcher_health()
    return {
        "watching": get_watch_count(),
        "deaths_detected": get_death_count(),
        "rss_feed": f"{base_url(request)}/rss",
        "people": f"{base_url(request)}/people",
        "sitemap": f"{base_url(request)}/sitemap.xml",
        "watcher_health": health,
        "watcher_is_stale": _watcher_is_stale(health),
    }


@app.get("/robots.txt", response_class=Response)
def robots(request: Request):
    content = f"User-agent: *\nAllow: /\nSitemap: {base_url(request)}/sitemap.xml\n"
    return Response(content=content, media_type="text/plain")


@app.get("/sitemap.xml", response_class=Response)
def sitemap(request: Request):
    site = base_url(request)
    paths = ["/", "/people", "/deaths", "/lists/most-monitored", "/lists/oldest-living", "/lists/actors", "/lists/musicians"]
    paths += [f"/person/{p['slug']}" for p in CATALOG]
    urls = "\n".join(
        f"  <url><loc>{e(site + path)}</loc><changefreq>daily</changefreq><priority>{'1.0' if path == '/' else '0.7'}</priority></url>"
        for path in paths
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n'
    return Response(content=xml, media_type="application/xml; charset=utf-8")


@app.get("/skull.png", response_class=Response)
def skull_icon():
    import pathlib
    skull_path = pathlib.Path(__file__).parent / "skull.png"
    data = skull_path.read_bytes()
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "public, max-age=300"})


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    deaths = get_deaths(5)
    watched_count = get_watch_count()
    deaths_count = get_death_count()
    alerts_html = (
        '<div class="alert-card" style="justify-content:center;color:var(--mv-text-quaternary);font-size:13px;">no deaths detected yet</div>'
        if not deaths else "".join(death_card(r) for r in deaths)
    )

    body = f"""
  <section class="hero">
    <img src="/skull.png?v=3" alt="mortivox" style="width:72px;height:72px;margin-bottom:28px;image-rendering:pixelated;">
    <h1>mortivox</h1>
    <p class="tagline">paste a wikipedia link. get notified the exact moment someone dies.</p>
    <div class="input-group" id="step1">
      <input type="url" placeholder="https://en.wikipedia.org/wiki/..." id="wikiUrl" autocomplete="off">
      <button id="nextBtn">next →</button>
    </div>
    <div id="step2">
      <div class="person-card">
        <div class="person-thumb-placeholder" id="personThumbPlaceholder">?</div>
        <img class="person-thumb" id="personThumb" src="" alt="" style="display:none">
        <div class="person-info">
          <div class="pname" id="personName"></div>
          <div class="pdesc" id="personDesc"></div>
        </div>
      </div>
      <div class="input-group">
        <input type="email" placeholder="your@email.com" id="emailInput" autocomplete="email">
        <button id="monitorBtn">monitor →</button>
      </div>
      <button class="back-btn" id="backBtn">← change link</button>
    </div>
    <div class="success-msg" id="successMsg">
      <div class="success-icon">✓</div>
      <span id="successText">monitoring started</span>
      <button class="back-btn" onclick="resetFlow()">monitor another person</button>
    </div>
    <p class="hint" id="mainHint">works with any wikipedia page in any language</p>
    <a href="#how" class="scroll-down"><span>how it works</span><span>↓</span></a>
  </section>

  <section class="section" id="how">
    <div class="section-title">how it works</div>
    <div class="steps">
      <div class="step"><div class="step-num">1</div><div class="step-body"><h3>paste the link</h3><p>any wikipedia page, in any language</p></div></div>
      <div class="step"><div class="step-num">2</div><div class="step-body"><h3>we watch</h3><p>our system monitors wikipedia 24/7 via the live edit stream</p></div></div>
      <div class="step"><div class="step-num">3</div><div class="step-body"><h3>you get notified</h3><p>instant email the moment a death is detected</p></div></div>
    </div>
  </section>

  <section class="section">
    <div class="section-title">by the numbers</div>
    <div class="stats-grid">
      <div class="stat-card"><div class="num">{watched_count}</div><div class="label">pages monitored</div></div>
      <div class="stat-card"><div class="num">{deaths_count}</div><div class="label">deaths detected</div></div>
      <div class="stat-card"><div class="num">&lt;1min</div><div class="label">target detection time</div></div>
    </div>
  </section>

  <section class="section">
    <div class="section-title">recent detections</div>
    <div class="alerts-list" style="max-width:520px;margin:0 auto;display:flex;flex-direction:column;gap:8px">{alerts_html}</div>
  </section>

  <section class="section">
    <div class="section-title">public watchlists</div>
    <div class="list-grid container">
      <a class="panel" href="/people"><div class="card-body"><div class="card-title">People directory</div><div class="card-meta">Public pages created for search and sharing</div></div></a>
      <a class="panel" href="/lists/most-monitored"><div class="card-body"><div class="card-title">Most monitored</div><div class="card-meta">Pages with the most subscribers</div></div></a>
      <a class="panel" href="/lists/actors"><div class="card-body"><div class="card-title">Actors</div><div class="card-meta">Film and television watchlist</div></div></a>
      <a class="panel" href="/lists/musicians"><div class="card-body"><div class="card-title">Musicians</div><div class="card-meta">Music watchlist</div></div></a>
    </div>
  </section>

  {footer()}

  <script>
    function extractTitle(url) {{
      try {{
        const u = new URL(url.trim());
        if (!u.hostname.includes('wikipedia.org')) return null;
        const parts = u.pathname.split('/wiki/');
        return (parts.length>=2 && parts[1]) ? decodeURIComponent(parts[1]) : null;
      }} catch {{ return null; }}
    }}
    function slugifyTitle(t) {{ return t.toLowerCase().replace(/_/g,'-').replace(/[^a-z0-9-]/g,'').replace(/-+/g,'-').replace(/^-|-$/g,''); }}
    function fmt(t) {{ return t.replace(/_/g,' '); }}
    let currentTitle = null;
    document.getElementById('nextBtn').addEventListener('click', goToStep2);
    document.getElementById('wikiUrl').addEventListener('keypress', e => {{ if(e.key==='Enter') goToStep2(); }});
    async function goToStep2() {{
      const title = extractTitle(document.getElementById('wikiUrl').value);
      if (!title) {{
        const i=document.getElementById('wikiUrl');
        i.style.outline='1px solid var(--mv-danger)';
        setTimeout(()=>i.style.outline='',1500); return;
      }}
      currentTitle = title;
      document.getElementById('step1').style.display='none';
      document.getElementById('step2').classList.add('visible');
      document.getElementById('mainHint').style.display='none';
      document.getElementById('personName').textContent=fmt(title);
      document.getElementById('emailInput').focus();
      try {{
        const apiUrl = `https://en.wikipedia.org/w/api.php?action=query&titles=${{encodeURIComponent(title.replace(/_/g,' '))}}&prop=pageimages|description&pithumbsize=300&redirects=true&format=json&origin=*`;
        const r = await fetch(apiUrl);
        if(r.ok) {{
          const data = await r.json();
          const page = Object.values(data.query.pages)[0];
          if(page && !page.missing) {{
            if(page.description) document.getElementById('personDesc').textContent = page.description;
            if(page.thumbnail && page.thumbnail.source) {{
              const img = document.getElementById('personThumb');
              img.src = page.thumbnail.source;
              img.style.display = 'block';
              document.getElementById('personThumbPlaceholder').style.display = 'none';
            }}
          }}
        }}
      }} catch {{}}
    }}
    document.getElementById('backBtn').addEventListener('click',()=>{{
      document.getElementById('step2').classList.remove('visible');
      document.getElementById('step1').style.display='';
      document.getElementById('mainHint').style.display='';
      document.getElementById('personThumb').style.display='none';
      document.getElementById('personThumbPlaceholder').style.display='flex';
      currentTitle=null;
    }});
    document.getElementById('monitorBtn').addEventListener('click',submitWatch);
    document.getElementById('emailInput').addEventListener('keypress',e=>{{if(e.key==='Enter')submitWatch();}});
    async function submitWatch() {{
      if(!currentTitle) return;
      trackEvent('click_monitor', {{wiki_title: currentTitle, slug: slugifyTitle(currentTitle), page_type: 'home'}});
      const email=document.getElementById('emailInput').value.trim();
      if(!email||!email.includes('@')) {{
        const i=document.getElementById('emailInput');
        i.style.outline='1px solid var(--mv-danger)';
        setTimeout(()=>i.style.outline='',1500); return;
      }}
      const btn=document.getElementById('monitorBtn');
      btn.textContent='...'; btn.disabled=true;
      trackEvent('submit_watch', {{wiki_title: currentTitle, slug: slugifyTitle(currentTitle)}});
      try {{
        const r=await fetch('/watch',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{wiki_title:currentTitle,email}})}});
        const d=await r.json();
        document.getElementById('step2').classList.remove('visible');
        document.getElementById('successMsg').classList.add('visible');
        const success = document.getElementById('successText');
        success.textContent = '';
        const prefix = (d.added ? 'now monitoring ' : 'already watching ') + fmt(currentTitle) + ' · ';
        success.appendChild(document.createTextNode(prefix));
        const link = document.createElement('a');
        link.href = '/person/' + slugifyTitle(currentTitle);
        link.textContent = 'public page';
        success.appendChild(link);
        document.getElementById('mainHint').style.display='none';
        trackEvent('watch_success', {{wiki_title: currentTitle, slug: slugifyTitle(currentTitle), success: true}});
      }} catch(e) {{
        btn.innerHTML='error — try again';btn.disabled=false;
        trackEvent('watch_error', {{wiki_title: currentTitle, slug: slugifyTitle(currentTitle), success: false}});
      }}
    }}
    function resetFlow() {{
      currentTitle=null;
      document.getElementById('wikiUrl').value='';
      document.getElementById('emailInput').value='';
      document.getElementById('successMsg').classList.remove('visible');
      document.getElementById('step1').style.display='';
      document.getElementById('mainHint').style.display='';
      document.getElementById('personThumb').style.display='none';
      document.getElementById('personThumbPlaceholder').style.display='flex';
      const btn=document.getElementById('monitorBtn');
      btn.textContent='monitor →';
      btn.disabled=false;
    }}
  </script>
"""
    return layout(
        request,
        "mortivox — Wikipedia death alerts",
        "Paste a Wikipedia link and get notified when Mortivox detects a death-related change.",
        body,
        "/",
    )


@app.get("/people", response_class=HTMLResponse)
def people(request: Request):
    watched = sorted(get_all_watched_titles())
    people_by_title = {p["wiki_title"]: p for p in catalog_people()}
    for title in watched:
        people_by_title.setdefault(title, {
            "wiki_title": title,
            "display_name": title.replace("_", " "),
            "category": "User-monitored page",
            "slug": title_to_slug(title),
        })
    people = sorted(people_by_title.values(), key=lambda p: p.get("display_name", p["wiki_title"]).lower())
    cards = "".join(person_card(p) for p in people)
    body = f"""
    <main class="page"><div class="container">
      {nav()}
      <h1 class="title">People monitored by Mortivox</h1>
      <p class="lede">Public pages for Wikipedia profiles tracked by Mortivox. Status means what Mortivox has detected, not a separate biographical claim.</p>
      <div class="grid">{cards}</div>
    </div></main>{footer()}
    """
    return layout(request, "People monitored by Mortivox", "Browse public Mortivox pages for monitored Wikipedia profiles.", body, "/people")


@app.get("/deaths", response_class=HTMLResponse)
def deaths_page(request: Request):
    deaths = get_deaths(100)
    if deaths:
        content = "".join(death_card(r) for r in deaths)
    else:
        content = """
        <div class="panel" style="display:block;text-align:center;padding:36px">
          <div class="card-title" style="margin-bottom:8px">No deaths detected yet.</div>
          <div class="card-meta">Mortivox monitors Wikipedia pages and records confirmed death-related changes when they appear.</div>
          <div style="margin-top:22px"><a class="button secondary" href="/people">browse monitored people</a></div>
        </div>
        """
    body = f"""
    <main class="page"><div class="container">
      {nav()}
      <h1 class="title">Detected deaths</h1>
      <p class="lede">A public log of death-related Wikipedia changes detected by Mortivox.</p>
      <div style="display:flex;flex-direction:column;gap:8px">{content}</div>
    </div></main>{footer()}
    """
    return layout(request, "Detected deaths — Mortivox", "A public log of death-related Wikipedia changes detected by Mortivox.", body, "/deaths")


@app.get("/person/{slug}", response_class=HTMLResponse)
def public_person(slug: str, request: Request):
    catalog_person = find_catalog_person(slug)
    title = catalog_person["wiki_title"] if catalog_person else slug.replace("-", "_").title().replace("_", "_")
    info = get_person_info(title)
    if not info and not catalog_person:
        raise HTTPException(404, "Person not found")

    name = (info or {}).get("name") or (catalog_person or {}).get("display_name") or title.replace("_", " ")
    canonical_slug = title_to_slug((info or {}).get("title") or title)
    category = catalog_person.get("category") if catalog_person else (info or {}).get("occupation") or "Public figure"
    description = (info or {}).get("description") or category
    extract = (info or {}).get("extract") or "Mortivox monitors this Wikipedia page for death-related changes."
    thumb = (info or {}).get("thumbnail")
    birth = (info or {}).get("birth_date") or (info or {}).get("birth_year") or (catalog_person or {}).get("birth_year")
    death = get_death_for_title((info or {}).get("title") or title)
    watch_count = get_watch_count_for_title((info or {}).get("title") or title)
    # Wording deliberately avoids asserting the person is alive. Mortivox only
    # reports what it has detected in its own database, not a biographical claim.
    status_sentence = (
        f"Mortivox has detected a death update for {name}."
        if death else
        "Mortivox has not detected a death update for this Wikipedia page."
    )
    status = "death update detected" if death else "no death update detected by Mortivox"
    badge = "danger" if death else "ok"
    image = f'<img class="avatar" src="{e(thumb)}" alt="{e(name)}">' if thumb else f'<div class="avatar-placeholder">{e(name[:1])}</div>'

    death_block = ""
    if death:
        death_block = f"""
        <div class="panel" style="display:block;margin:24px 0">
          <div class="card-title">Death detected</div>
          <div class="card-meta">Detected {e(str(death.get("detected_at", ""))[:10])}. Death date field: {e(death.get("death_date") or "not confirmed")}</div>
          {f'<p style="margin-top:12px"><a class="button secondary" href="{e(death.get("edit_url"))}">view detected edit</a></p>' if death.get("edit_url") else ""}
        </div>
        """

    canonical_title = (info or {}).get("title") or title
    watch_href = f"/?watch={e(canonical_title)}"
    monitor_click_js = (
        f'trackEvent("click_monitor", {{"wiki_title": {js(canonical_title)}, '
        f'"slug": {js(canonical_slug)}, "page_type": "person", "category": {js(category)}}})'
    )

    body = f"""
    <main class="page"><div class="container">
      {nav()}
      <section class="person-hero">
        {image}
        <div>
          <h1 class="title">{e(name)}</h1>
          <p class="lede" style="margin:0">{e(description)}</p>
        </div>
      </section>
      <div class="kv">
        <div><strong>Status</strong><span><span class="badge {badge}">{e(status)}</span></span></div>
        <div><strong>Watchers</strong><span>{watch_count}</span></div>
        <div><strong>Category</strong><span>{e(category)}</span></div>
        <div><strong>Birth info</strong><span>{e(birth or "unknown")}</span></div>
      </div>
      {death_block}
      <div class="panel" style="display:block">
        <div class="card-title" style="margin-bottom:8px">Is {e(name)} being monitored?</div>
        <p class="card-meta" style="font-size:14px;line-height:1.7">{e(status_sentence)} Mortivox is watching this Wikipedia page and will keep checking for updates.</p>
      </div>
      <div class="panel" style="display:block;margin-top:12px">
        <div class="card-title" style="margin-bottom:8px">How Mortivox detects changes</div>
        <p class="card-meta" style="font-size:14px;line-height:1.7">Mortivox listens to Wikipedia's live edit stream and checks watched pages for death-related infobox changes shortly after they are published.</p>
      </div>
      <div class="panel" style="display:block;margin-top:12px">
        <div class="card-title" style="margin-bottom:8px">How to get notified</div>
        <p class="card-meta" style="font-size:14px;line-height:1.7">Enter your email on the Mortivox homepage for this Wikipedia page to receive an alert if a death update is detected.</p>
      </div>
      <div class="panel" style="display:block;margin-top:24px">
        <div class="card-title" style="margin-bottom:8px">About this page</div>
        <p class="card-meta" style="font-size:14px;line-height:1.7">{e(extract)}</p>
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:22px">
          <a class="button" href="{e(wiki_url((info or {}).get("title") or title))}" target="_blank" rel="noopener">view Wikipedia</a>
          <a class="button secondary" href="{watch_href}" onclick="{e(monitor_click_js)}">monitor this person</a>
        </div>
      </div>
    </div></main>{footer()}
    <script>
      trackEvent('view_person_page', {{
        wiki_title: {js(canonical_title)},
        slug: {js(canonical_slug)},
        page_type: 'person',
        category: {js(category)}
      }});
    </script>
    """
    return layout(
        request,
        f"{name} — Mortivox watch page",
        f"Mortivox watch page for {name}. Current Mortivox status: {status}.",
        body,
        f"/person/{canonical_slug}",
        "/skull.png?v=3",
    )


@app.get("/lists/{list_slug}", response_class=HTMLResponse)
def list_page(list_slug: str, request: Request):
    list_meta = LISTS.get(list_slug)
    if not list_meta:
        raise HTTPException(404, "List not found")

    if list_slug == "most-monitored":
        counts = get_watch_counts()
        titles = sorted(get_all_watched_titles(), key=lambda t: counts.get(t, 0), reverse=True)
        people = [{
            "wiki_title": t,
            "display_name": t.replace("_", " "),
            "category": f"{counts.get(t, 0)} watcher(s)",
            "slug": title_to_slug(t),
        } for t in titles[:80]]
        if not people:
            people = catalog_people()[:40]
    elif list_slug == "oldest-living":
        people = [p for p in catalog_people() if p.get("birth_year")]
        people = sorted(people, key=lambda p: p.get("birth_year") or 9999)[:60]
    else:
        people = get_list_people(list_slug)[:80]

    cards = "".join(person_card(p) for p in people)
    body = f"""
    <main class="page"><div class="container">
      {nav()}
      <h1 class="title">{e(list_meta["title"])}</h1>
      <p class="lede">{e(list_meta["description"])}</p>
      <div class="grid">{cards}</div>
    </div></main>{footer()}
    """
    return layout(request, f"{list_meta['title']} — Mortivox", list_meta["description"], body, f"/lists/{list_slug}")
