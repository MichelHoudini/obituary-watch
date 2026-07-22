"""
main.py — FastAPI application.
Serves the management API and the public landing page.
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

app = FastAPI(title="Mortivox", version="2.0.0")

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


# ── RSS feeds ─────────────────────────────────────────────────────────────────

@app.get("/rss", response_class=Response)
def global_rss_feed(request: Request):
    feed = build_global_feed(base_url(request))
    return Response(content=feed, media_type="application/atom+xml")


@app.get("/rss/{list_slug}", response_class=Response)
def list_rss_feed(list_slug: str, request: Request):
    feed = build_list_feed(list_slug, base_url(request))
    if feed is None:
        raise HTTPException(status_code=404, detail=f"List {list_slug!r} not found")
    return Response(content=feed, media_type="application/atom+xml")


# ── Watchlist management ──────────────────────────────────────────────────────

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

    return {
        "added": is_new,
        "wiki_title": title,
        "display_name": name,
        "message": "Added" if is_new else "Already watching",
    }


@app.post("/watch/category")
def add_category(req: CategoryRequest):
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
    return [dict(r) for r in get_all_watched()]


@app.get("/deaths")
def list_deaths(limit: int = 50):
    return [dict(r) for r in get_deaths(limit)]


@app.get("/search")
def search(q: str, limit: int = 8):
    return search_person(q, limit)


@app.get("/status")
def status(request: Request):
    watched = get_watched_titles()
    rss_url = f"{base_url(request)}/rss"
    return {
        "watching": len(watched),
        "deaths_detected": len(get_deaths(limit=9999)),
        "rss_feed": rss_url,
    }


@app.get("/categories")
def list_categories():
    return list(CATEGORY_QCODES.keys())


@app.get("/robots.txt", response_class=Response)
def robots():
    return Response(content="User-agent: *\nAllow: /\n", media_type="text/plain")


# ── Landing page ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    watched = get_all_watched()
    deaths  = get_deaths(limit=5)

    if not deaths:
        alerts_html = """
        <div class="alert-card" style="justify-content:center;color:var(--mv-text-quaternary);font-size:13px;">
          no deaths detected yet
        </div>"""
    else:
        alerts_html = "".join(
            f"""<a class="alert-card" href="{r['wiki_url']}" target="_blank">
              <div class="alert-dot"></div>
              <div class="alert-info">
                <div class="name">{r['display_name']}</div>
                <div class="when">detected {r['detected_at'][:10]}</div>
              </div>
              <span class="alert-badge">{r['death_date'] or 'confirmed'}</span>
            </a>"""
            for r in deaths
        )

    watched_count = len(watched)
    deaths_count  = len(get_deaths(limit=9999))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>mortivox</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {{
      --mv-bg: #0a0a0a; --mv-surface: #111111; --mv-surface-raised: #1a1a1a;
      --mv-surface-muted: #0d0d0d; --mv-border: #222222; --mv-border-hover: #333333;
      --mv-text-primary: #f0f0f0; --mv-text-secondary: #a0a0a0;
      --mv-text-tertiary: #707070; --mv-text-quaternary: #505050;
      --mv-danger: #e74c3c; --mv-danger-glow: rgba(231,76,60,0.4);
      --mv-positive: #2ecc71;
      --mv-radius-sm: 6px; --mv-radius-md: 10px; --mv-radius-lg: 12px;
      --mv-transition: 150ms ease-out;
    }}
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html {{ scroll-behavior: smooth; }}
    body {{ font-family: 'Inter', -apple-system, sans-serif; background: var(--mv-bg); color: var(--mv-text-primary); line-height: 1.5; -webkit-font-smoothing: antialiased; }}
    a {{ color: inherit; text-decoration: none; }}
    .hero {{ min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 48px 20px; position: relative; }}
    .hero::before {{ content: ''; position: absolute; top: 0; left: 50%; transform: translateX(-50%); width: min(600px,80%); height: 1px; background: linear-gradient(90deg,transparent,var(--mv-border),transparent); }}
    .mark {{ width: 44px; height: 44px; margin-bottom: 32px; display: flex; align-items: center; justify-content: center; border-radius: var(--mv-radius-lg); border: 1px solid var(--mv-border); background: var(--mv-surface-muted); }}
    .mark svg {{ width: 20px; height: 20px; color: var(--mv-text-secondary); }}
    .hero h1 {{ font-size: clamp(36px,8vw,64px); font-weight: 500; letter-spacing: -0.02em; line-height: 1.05; margin-bottom: 16px; }}
    .hero .tagline {{ font-size: 16px; color: var(--mv-text-tertiary); max-width: 380px; margin-bottom: 40px; line-height: 1.6; }}
    .step-indicator {{ display: flex; gap: 6px; margin-bottom: 24px; }}
    .step-dot {{ width: 6px; height: 6px; border-radius: 50%; background: var(--mv-border); transition: background var(--mv-transition); }}
    .step-dot.active {{ background: var(--mv-text-primary); }}
    .input-group {{ display: flex; width: 100%; max-width: 520px; border-radius: var(--mv-radius-md); border: 1px solid var(--mv-border); background: var(--mv-surface); overflow: hidden; transition: border-color var(--mv-transition); }}
    .input-group:focus-within {{ border-color: var(--mv-text-primary); }}
    .input-group input {{ flex: 1; padding: 16px 20px; border: none; outline: none; background: transparent; font-size: 15px; color: var(--mv-text-primary); font-family: inherit; }}
    .input-group input::placeholder {{ color: var(--mv-text-quaternary); }}
    .input-group button {{ padding: 16px 28px; border: none; outline: none; background: var(--mv-text-primary); color: var(--mv-bg); font-size: 14px; font-weight: 500; cursor: pointer; white-space: nowrap; display: flex; align-items: center; gap: 8px; font-family: inherit; transition: opacity var(--mv-transition); }}
    .input-group button:hover {{ opacity: 0.85; }}
    .input-group button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
    .input-group button svg {{ width: 14px; height: 14px; }}
    .hint {{ margin-top: 12px; font-size: 12px; color: var(--mv-text-quaternary); }}
    #step2 {{ display: none; width: 100%; max-width: 520px; flex-direction: column; align-items: center; gap: 12px; }}
    #step2.visible {{ display: flex; }}
    .back-btn {{ font-size: 12px; color: var(--mv-text-quaternary); cursor: pointer; background: none; border: none; font-family: inherit; padding: 4px 0; transition: color var(--mv-transition); }}
    .back-btn:hover {{ color: var(--mv-text-secondary); }}
    .person-preview {{ width: 100%; padding: 14px 18px; border-radius: var(--mv-radius-md); border: 1px solid var(--mv-border); background: var(--mv-surface); font-size: 14px; color: var(--mv-text-secondary); text-align: left; }}
    .person-preview strong {{ color: var(--mv-text-primary); }}
    .success-msg {{ display: none; flex-direction: column; align-items: center; gap: 12px; color: var(--mv-text-secondary); font-size: 14px; }}
    .success-msg.visible {{ display: flex; }}
    .success-icon {{ width: 44px; height: 44px; border-radius: 50%; background: color-mix(in srgb, var(--mv-positive) 12%, transparent); border: 1px solid color-mix(in srgb, var(--mv-positive) 30%, transparent); display: flex; align-items: center; justify-content: center; }}
    .success-icon svg {{ width: 20px; height: 20px; color: var(--mv-positive); }}
    .scroll-down {{ position: absolute; bottom: 32px; display: flex; flex-direction: column; align-items: center; gap: 6px; color: var(--mv-text-quaternary); font-size: 11px; letter-spacing: 0.05em; animation: float 3s ease-in-out infinite; }}
    .scroll-down svg {{ width: 16px; height: 16px; }}
    @keyframes float {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(6px); }} }}
    .section {{ padding: 80px 20px; border-top: 1px solid var(--mv-border); }}
    .section-title {{ text-align: center; font-size: 11px; font-weight: 500; color: var(--mv-text-quaternary); text-transform: uppercase; letter-spacing: 0.12em; margin-bottom: 48px; }}
    .steps {{ display: flex; flex-direction: column; gap: 40px; max-width: 720px; margin: 0 auto; }}
    .step {{ display: flex; align-items: flex-start; gap: 20px; }}
    .step-num {{ width: 36px; height: 36px; border-radius: var(--mv-radius-sm); border: 1px solid var(--mv-border); display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 500; color: var(--mv-text-tertiary); flex-shrink: 0; }}
    .step-body h3 {{ font-size: 16px; font-weight: 500; margin-bottom: 6px; }}
    .step-body p {{ font-size: 14px; color: var(--mv-text-tertiary); line-height: 1.6; }}
    .stats-grid {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 16px; max-width: 600px; margin: 0 auto; }}
    .stat-card {{ text-align: center; padding: 28px 16px; border-radius: var(--mv-radius-md); border: 1px solid var(--mv-border); background: var(--mv-surface); transition: border-color var(--mv-transition), background var(--mv-transition); }}
    .stat-card:hover {{ border-color: var(--mv-border-hover); background: var(--mv-surface-raised); }}
    .stat-card svg {{ width: 20px; height: 20px; color: var(--mv-text-secondary); margin-bottom: 12px; }}
    .stat-card .num {{ font-size: 28px; font-weight: 500; font-variant-numeric: tabular-nums; line-height: 1.1; margin-bottom: 6px; }}
    .stat-card .label {{ font-size: 12px; color: var(--mv-text-tertiary); }}
    .alerts-list {{ max-width: 520px; margin: 0 auto; display: flex; flex-direction: column; gap: 8px; }}
    .alert-card {{ display: flex; align-items: center; gap: 14px; padding: 16px 18px; border-radius: var(--mv-radius-md); border: 1px solid var(--mv-border); background: var(--mv-surface); transition: border-color var(--mv-transition), background var(--mv-transition); }}
    .alert-card:hover {{ border-color: var(--mv-border-hover); background: var(--mv-surface-raised); }}
    .alert-dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--mv-danger); box-shadow: 0 0 8px var(--mv-danger-glow); flex-shrink: 0; animation: pulse 2s ease-in-out infinite; }}
    @keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
    .alert-info {{ flex: 1; min-width: 0; }}
    .alert-info .name {{ font-size: 15px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .alert-info .when {{ font-size: 12px; color: var(--mv-text-quaternary); margin-top: 2px; }}
    .alert-badge {{ font-size: 11px; font-weight: 500; padding: 4px 10px; border-radius: 4px; background: color-mix(in srgb, var(--mv-danger) 10%, transparent); color: var(--mv-danger); white-space: nowrap; flex-shrink: 0; }}
    .footer {{ text-align: center; padding: 40px 20px; border-top: 1px solid var(--mv-border); }}
    .footer .candle {{ width: 18px; height: 18px; margin: 0 auto 10px; color: var(--mv-text-quaternary); }}
    .footer p {{ font-size: 12px; color: var(--mv-text-quaternary); }}
    .footer .links {{ display: flex; justify-content: center; gap: 24px; margin-top: 16px; }}
    .footer .links a {{ font-size: 12px; color: var(--mv-text-quaternary); transition: color var(--mv-transition); }}
    .footer .links a:hover {{ color: var(--mv-text-secondary); }}
    @media (min-width: 640px) {{ .steps {{ flex-direction: row; gap: 48px; }} .step {{ flex-direction: column; align-items: center; text-align: center; flex: 1; }} }}
    @media (max-width: 480px) {{ .stats-grid {{ grid-template-columns: 1fr; }} .input-group {{ flex-direction: column; }} .input-group button {{ justify-content: center; }} }}
  </style>
</head>
<body>
  <section class="hero">
    <div class="mark">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Z"/><path d="M12 8v4l3 3"/><path d="M8 22v-2a4 4 0 0 1 8 0v2"/>
      </svg>
    </div>
    <h1>mortivox</h1>
    <p class="tagline">paste a wikipedia link. get notified the exact moment someone dies.</p>
    <div class="step-indicator">
      <div class="step-dot active" id="dot1"></div>
      <div class="step-dot" id="dot2"></div>
    </div>
    <div class="input-group" id="step1">
      <input type="url" placeholder="https://en.wikipedia.org/wiki/..." id="wikiUrl" autocomplete="off">
      <button id="nextBtn">next
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
      </button>
    </div>
    <div id="step2">
      <div class="person-preview">watching <strong id="personName"></strong></div>
      <div class="input-group">
        <input type="email" placeholder="your@email.com" id="emailInput" autocomplete="email">
        <button id="monitorBtn">monitor
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
        </button>
      </div>
      <button class="back-btn" id="backBtn">&#8592; change link</button>
    </div>
    <div class="success-msg" id="successMsg">
      <div class="success-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
      </div>
      <span id="successText">monitoring started</span>
      <button class="back-btn" onclick="resetFlow()">monitor another person</button>
    </div>
    <p class="hint" id="mainHint">works with any wikipedia page in any language</p>
    <a href="#how" class="scroll-down">
      <span>how it works</span>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="m19 12-7 7-7-7"/></svg>
    </a>
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
      <div class="stat-card">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
        <div class="num">{watched_count}</div><div class="label">pages monitored</div>
      </div>
      <div class="stat-card">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 17H2a3 3 0 0 0 3-3V9a7 7 0 0 1 14 0v5a3 3 0 0 0 3 3Z"/><path d="M12 22v-3"/></svg>
        <div class="num">{deaths_count}</div><div class="label">deaths detected</div>
      </div>
      <div class="stat-card">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
        <div class="num">&lt;1min</div><div class="label">detection time</div>
      </div>
    </div>
  </section>

  <section class="section">
    <div class="section-title">recent detections</div>
    <div class="alerts-list">{alerts_html}</div>
  </section>

  <footer class="footer">
    <svg class="candle" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 22c4.97 0 9-2.24 9-5s-4.03-5-9-5-9 2.24-9 5 4.03 5 9 5Z"/><path d="M12 12V7"/><path d="M12 7c1.5-2 0-4-1-5 0 2-1.5 3-1 5"/>
    </svg>
    <p>mortivox &mdash; silent watch, respectful notification</p>
    <div class="links"><a href="/rss">rss feed</a><a href="/deaths">all deaths</a></div>
  </footer>

  <script>
    function extractTitle(url) {{
      try {{
        const u = new URL(url.trim());
        if (!u.hostname.includes('wikipedia.org')) return null;
        const parts = u.pathname.split('/wiki/');
        if (parts.length < 2 || !parts[1]) return null;
        return decodeURIComponent(parts[1]);
      }} catch {{ return null; }}
    }}
    function formatName(t) {{ return t.replace(/_/g,' '); }}
    let currentTitle = null;
    document.getElementById('nextBtn').addEventListener('click', goToStep2);
    document.getElementById('wikiUrl').addEventListener('keypress', e => {{ if(e.key==='Enter') goToStep2(); }});
    function goToStep2() {{
      const title = extractTitle(document.getElementById('wikiUrl').value);
      if (!title) {{
        const i = document.getElementById('wikiUrl');
        i.style.outline = '1px solid var(--mv-danger)';
        setTimeout(() => i.style.outline='', 1500); return;
      }}
      currentTitle = title;
      document.getElementById('personName').textContent = formatName(title);
      document.getElementById('step1').style.display = 'none';
      document.getElementById('step2').classList.add('visible');
      document.getElementById('dot1').classList.remove('active');
      document.getElementById('dot2').classList.add('active');
      document.getElementById('mainHint').style.display = 'none';
      document.getElementById('emailInput').focus();
    }}
    document.getElementById('backBtn').addEventListener('click', () => {{
      document.getElementById('step2').classList.remove('visible');
      document.getElementById('step1').style.display = '';
      document.getElementById('dot1').classList.add('active');
      document.getElementById('dot2').classList.remove('active');
      document.getElementById('mainHint').style.display = '';
      currentTitle = null;
    }});
    document.getElementById('monitorBtn').addEventListener('click', submitWatch);
    document.getElementById('emailInput').addEventListener('keypress', e => {{ if(e.key==='Enter') submitWatch(); }});
    async function submitWatch() {{
      if (!currentTitle) return;
      const btn = document.getElementById('monitorBtn');
      btn.textContent = '...'; btn.disabled = true;
      try {{
        const r = await fetch('/watch', {{
          method: 'POST',
          headers: {{'Content-Type':'application/json'}},
          body: JSON.stringify({{ wiki_title: currentTitle }})
        }});
        const d = await r.json();
        document.getElementById('step2').classList.remove('visible');
        document.getElementById('successMsg').classList.add('visible');
        document.getElementById('successText').textContent =
          d.added ? 'now monitoring '+formatName(currentTitle) : 'already watching '+formatName(currentTitle);
        document.getElementById('mainHint').style.display = 'none';
      }} catch(e) {{
        btn.innerHTML = 'error &mdash; try again'; btn.disabled = false;
      }}
    }}
    function resetFlow() {{
      currentTitle = null;
      document.getElementById('wikiUrl').value = '';
      document.getElementById('emailInput').value = '';
      document.getElementById('successMsg').classList.remove('visible');
      document.getElementById('step1').style.display = '';
      document.getElementById('dot1').classList.add('active');
      document.getElementById('dot2').classList.remove('active');
      document.getElementById('mainHint').style.display = '';
    }}
  </script>
</body>
</html>"""