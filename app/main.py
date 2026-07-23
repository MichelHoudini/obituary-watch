"""
main.py - FastAPI app for Mortivox.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.db import (
    init_db, add_watch, get_all_watched_titles,
    get_deaths, get_watch_count, get_death_count,
)
from app.wiki import title_from_url, get_person_info
from app.rss import build_global_feed

app = FastAPI(title="Mortivox", version="3.0.0")

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


@app.get("/rss", response_class=Response)
def global_rss_feed(request: Request):
    feed = build_global_feed(base_url(request))
    return Response(content=feed, media_type="application/atom+xml")


class WatchRequest(BaseModel):
    wiki_title: str
    email: str


@app.post("/watch")
def add_watch_endpoint(req: WatchRequest):
    if not req.wiki_title or not req.email:
        raise HTTPException(400, "wiki_title and email are required")
    is_new = add_watch(req.wiki_title, req.email)
    return {
        "added": is_new,
        "wiki_title": req.wiki_title,
        "message": "Added" if is_new else "Already watching",
    }


@app.get("/person")
def person_info(wiki_title: str):
    info = get_person_info(wiki_title)
    if not info:
        raise HTTPException(404, "Person not found")
    return info


@app.get("/deaths")
def list_deaths(limit: int = 50):
    return get_deaths(limit)


@app.get("/status")
def status(request: Request):
    return {
        "watching": get_watch_count(),
        "deaths_detected": get_death_count(),
        "rss_feed": f"{base_url(request)}/rss",
    }


@app.get("/robots.txt", response_class=Response)
def robots():
    return Response(content="User-agent: *\nAllow: /\n", media_type="text/plain")


@app.get("/skull.png", response_class=Response)
def skull_icon():
    import base64
    _b = "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"
    return Response(content=base64.b64decode(_b), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    deaths = get_deaths(5)
    watched_count = get_watch_count()
    deaths_count = get_death_count()

    if not deaths:
        alerts_html = '<div class="alert-card" style="justify-content:center;color:var(--mv-text-quaternary);font-size:13px;">no deaths detected yet</div>'
    else:
        alerts_html = "".join(
            f'<a class="alert-card" href="{r["wiki_url"]}" target="_blank">'
            f'<div class="alert-dot"></div>'
            f'<div class="alert-info">'
            f'<div class="name">{r["display_name"]}</div>'
            f'<div class="when">detected {r["detected_at"][:10]}</div>'
            f'</div>'
            f'<span class="alert-badge">{r["death_date"] or "confirmed"}</span>'
            f'</a>'
            for r in deaths
        )

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
    :root {{--mv-bg:#0a0a0a;--mv-surface:#111;--mv-surface-raised:#1a1a1a;--mv-surface-muted:#0d0d0d;--mv-border:#222;--mv-border-hover:#333;--mv-text-primary:#f0f0f0;--mv-text-secondary:#a0a0a0;--mv-text-tertiary:#707070;--mv-text-quaternary:#505050;--mv-danger:#e74c3c;--mv-danger-glow:rgba(231,76,60,0.4);--mv-positive:#2ecc71;--mv-radius-sm:6px;--mv-radius-md:10px;--mv-radius-lg:12px;--mv-transition:150ms ease-out}}
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    html{{scroll-behavior:smooth}}
    body{{font-family:'Inter',-apple-system,sans-serif;background:var(--mv-bg);color:var(--mv-text-primary);line-height:1.5;-webkit-font-smoothing:antialiased}}
    a{{color:inherit;text-decoration:none}}
    .hero{{min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:48px 20px;position:relative}}
    .hero::before{{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);width:min(600px,80%);height:1px;background:linear-gradient(90deg,transparent,var(--mv-border),transparent)}}
    .mark{{width:44px;height:44px;margin-bottom:32px;display:flex;align-items:center;justify-content:center;border-radius:var(--mv-radius-lg);border:1px solid var(--mv-border);background:var(--mv-surface-muted)}}
    .mark svg{{width:20px;height:20px;color:var(--mv-text-secondary)}}
    .hero h1{{font-size:clamp(36px,8vw,64px);font-weight:500;letter-spacing:-0.02em;line-height:1.05;margin-bottom:16px}}
    .hero .tagline{{font-size:16px;color:var(--mv-text-tertiary);max-width:380px;margin-bottom:40px;line-height:1.6}}
    .step-indicator{{display:flex;gap:6px;margin-bottom:24px}}
    .step-dot{{width:6px;height:6px;border-radius:50%;background:var(--mv-border);transition:background var(--mv-transition)}}
    .step-dot.active{{background:var(--mv-text-primary)}}
    .input-group{{display:flex;width:100%;max-width:520px;border-radius:var(--mv-radius-md);border:1px solid var(--mv-border);background:var(--mv-surface);overflow:hidden;transition:border-color var(--mv-transition)}}
    .input-group:focus-within{{border-color:var(--mv-text-primary)}}
    .input-group input{{flex:1;padding:16px 20px;border:none;outline:none;background:transparent;font-size:15px;color:var(--mv-text-primary);font-family:inherit}}
    .input-group input::placeholder{{color:var(--mv-text-quaternary)}}
    .input-group button{{padding:16px 28px;border:none;outline:none;background:var(--mv-text-primary);color:var(--mv-bg);font-size:14px;font-weight:500;cursor:pointer;white-space:nowrap;display:flex;align-items:center;gap:8px;font-family:inherit;transition:opacity var(--mv-transition)}}
    .input-group button:hover{{opacity:.85}}
    .input-group button:disabled{{opacity:.5;cursor:not-allowed}}
    .input-group button svg{{width:14px;height:14px}}
    .hint{{margin-top:12px;font-size:12px;color:var(--mv-text-quaternary)}}
    #step2{{display:none;width:100%;max-width:520px;flex-direction:column;align-items:center;gap:12px}}
    #step2.visible{{display:flex}}
    .back-btn{{font-size:12px;color:var(--mv-text-quaternary);cursor:pointer;background:none;border:none;font-family:inherit;padding:4px 0;transition:color var(--mv-transition)}}
    .back-btn:hover{{color:var(--mv-text-secondary)}}
    .person-card{{width:100%;padding:16px 18px;border-radius:var(--mv-radius-md);border:1px solid var(--mv-border);background:var(--mv-surface);text-align:left;display:flex;align-items:center;gap:14px}}
    .person-thumb{{width:44px;height:44px;border-radius:50%;object-fit:cover;border:1px solid var(--mv-border);flex-shrink:0}}
    .person-thumb-placeholder{{width:44px;height:44px;border-radius:50%;border:1px solid var(--mv-border);flex-shrink:0;background:var(--mv-surface-raised);display:flex;align-items:center;justify-content:center;color:var(--mv-text-quaternary);font-size:18px}}
    .person-info .pname{{font-size:15px;font-weight:500;color:var(--mv-text-primary)}}
    .person-info .pdesc{{font-size:12px;color:var(--mv-text-quaternary);margin-top:2px}}
    .success-msg{{display:none;flex-direction:column;align-items:center;gap:12px;color:var(--mv-text-secondary);font-size:14px}}
    .success-msg.visible{{display:flex}}
    .success-icon{{width:44px;height:44px;border-radius:50%;background:color-mix(in srgb,var(--mv-positive) 12%,transparent);border:1px solid color-mix(in srgb,var(--mv-positive) 30%,transparent);display:flex;align-items:center;justify-content:center}}
    .success-icon svg{{width:20px;height:20px;color:var(--mv-positive)}}
    .scroll-down{{position:absolute;bottom:32px;display:flex;flex-direction:column;align-items:center;gap:6px;color:var(--mv-text-quaternary);font-size:11px;letter-spacing:.05em;animation:float 3s ease-in-out infinite}}
    .scroll-down svg{{width:16px;height:16px}}
    @keyframes float{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(6px)}}}}
    .section{{padding:80px 20px;border-top:1px solid var(--mv-border)}}
    .section-title{{text-align:center;font-size:11px;font-weight:500;color:var(--mv-text-quaternary);text-transform:uppercase;letter-spacing:.12em;margin-bottom:48px}}
    .steps{{display:flex;flex-direction:column;gap:40px;max-width:720px;margin:0 auto}}
    .step{{display:flex;align-items:flex-start;gap:20px}}
    .step-num{{width:36px;height:36px;border-radius:var(--mv-radius-sm);border:1px solid var(--mv-border);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:500;color:var(--mv-text-tertiary);flex-shrink:0}}
    .step-body h3{{font-size:16px;font-weight:500;margin-bottom:6px}}
    .step-body p{{font-size:14px;color:var(--mv-text-tertiary);line-height:1.6}}
    .stats-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;max-width:600px;margin:0 auto}}
    .stat-card{{text-align:center;padding:28px 16px;border-radius:var(--mv-radius-md);border:1px solid var(--mv-border);background:var(--mv-surface);transition:border-color var(--mv-transition),background var(--mv-transition)}}
    .stat-card:hover{{border-color:var(--mv-border-hover);background:var(--mv-surface-raised)}}
    .stat-card svg{{width:20px;height:20px;color:var(--mv-text-secondary);margin-bottom:12px}}
    .stat-card .num{{font-size:28px;font-weight:500;font-variant-numeric:tabular-nums;line-height:1.1;margin-bottom:6px}}
    .stat-card .label{{font-size:12px;color:var(--mv-text-tertiary)}}
    .alerts-list{{max-width:520px;margin:0 auto;display:flex;flex-direction:column;gap:8px}}
    .alert-card{{display:flex;align-items:center;gap:14px;padding:16px 18px;border-radius:var(--mv-radius-md);border:1px solid var(--mv-border);background:var(--mv-surface);transition:border-color var(--mv-transition),background var(--mv-transition)}}
    .alert-card:hover{{border-color:var(--mv-border-hover);background:var(--mv-surface-raised)}}
    .alert-dot{{width:8px;height:8px;border-radius:50%;background:var(--mv-danger);box-shadow:0 0 8px var(--mv-danger-glow);flex-shrink:0;animation:pulse 2s ease-in-out infinite}}
    @keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.5}}}}
    .alert-info{{flex:1;min-width:0}}
    .alert-info .name{{font-size:15px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
    .alert-info .when{{font-size:12px;color:var(--mv-text-quaternary);margin-top:2px}}
    .alert-badge{{font-size:11px;font-weight:500;padding:4px 10px;border-radius:4px;background:color-mix(in srgb,var(--mv-danger) 10%,transparent);color:var(--mv-danger);white-space:nowrap;flex-shrink:0}}
    .footer{{text-align:center;padding:40px 20px;border-top:1px solid var(--mv-border)}}
    .footer .candle{{width:18px;height:18px;margin:0 auto 10px;color:var(--mv-text-quaternary)}}
    .footer p{{font-size:12px;color:var(--mv-text-quaternary)}}
    .footer .links{{display:flex;justify-content:center;gap:24px;margin-top:16px}}
    .footer .links a{{font-size:12px;color:var(--mv-text-quaternary);transition:color var(--mv-transition)}}
    .footer .links a:hover{{color:var(--mv-text-secondary)}}
    @media(min-width:640px){{.steps{{flex-direction:row;gap:48px}}.step{{flex-direction:column;align-items:center;text-align:center;flex:1}}}}
    @media(max-width:480px){{.stats-grid{{grid-template-columns:1fr}}.input-group{{flex-direction:column}}.input-group button{{justify-content:center}}}}
  </style>
</head>
<body>
  <section class="hero">
    <img src="/skull.png" alt="mortivox" style="width:72px;height:72px;margin-bottom:28px;mix-blend-mode:screen;opacity:0.92;image-rendering:pixelated;">

    <h1>mortivox</h1>
    <p class="tagline">paste a wikipedia link. get notified the exact moment someone dies.</p>
    <div class="step-indicator">
      <div class="step-dot active" id="dot1"></div>
      <div class="step-dot" id="dot2"></div>
    </div>
    <div class="input-group" id="step1">
      <input type="url" placeholder="https://en.wikipedia.org/wiki/..." id="wikiUrl" autocomplete="off">
      <button id="nextBtn">next<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg></button>
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
        <button id="monitorBtn">monitor<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg></button>
      </div>
      <button class="back-btn" id="backBtn">&#8592; change link</button>
    </div>
    <div class="success-msg" id="successMsg">
      <div class="success-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></div>
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
        return (parts.length>=2 && parts[1]) ? decodeURIComponent(parts[1]) : null;
      }} catch {{ return null; }}
    }}
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
      document.getElementById('dot1').classList.remove('active');
      document.getElementById('dot2').classList.add('active');
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
      document.getElementById('dot1').classList.add('active');
      document.getElementById('dot2').classList.remove('active');
      document.getElementById('mainHint').style.display='';
      document.getElementById('personThumb').style.display='none';
      document.getElementById('personThumbPlaceholder').style.display='flex';
      currentTitle=null;
    }});
    document.getElementById('monitorBtn').addEventListener('click',submitWatch);
    document.getElementById('emailInput').addEventListener('keypress',e=>{{if(e.key==='Enter')submitWatch();}});
    async function submitWatch() {{
      if(!currentTitle) return;
      const email=document.getElementById('emailInput').value.trim();
      if(!email||!email.includes('@')) {{
        const i=document.getElementById('emailInput');
        i.style.outline='1px solid var(--mv-danger)';
        setTimeout(()=>i.style.outline='',1500); return;
      }}
      const btn=document.getElementById('monitorBtn');
      btn.textContent='...'; btn.disabled=true;
      try {{
        const r=await fetch('/watch',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{wiki_title:currentTitle,email}})}});
        const d=await r.json();
        document.getElementById('step2').classList.remove('visible');
        document.getElementById('successMsg').classList.add('visible');
        document.getElementById('successText').textContent=d.added?'now monitoring '+fmt(currentTitle):'already watching '+fmt(currentTitle);
        document.getElementById('mainHint').style.display='none';
      }} catch(e) {{btn.innerHTML='error &mdash; try again';btn.disabled=false;}}
    }}
    function resetFlow() {{
      currentTitle=null;
      document.getElementById('wikiUrl').value='';
      document.getElementById('emailInput').value='';
      document.getElementById('successMsg').classList.remove('visible');
      document.getElementById('step1').style.display='';
      document.getElementById('dot1').classList.add('active');
      document.getElementById('dot2').classList.remove('active');
      document.getElementById('mainHint').style.display='';
      document.getElementById('personThumb').style.display='none';
      document.getElementById('personThumbPlaceholder').style.display='flex';
      const btn=document.getElementById('monitorBtn');
      btn.innerHTML='monitor <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>';
      btn.disabled=false;
    }}
  </script>
</body>
</html>"""