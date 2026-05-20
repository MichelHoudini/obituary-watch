"""
main.py — ObituaryWatch v3.
GET  /        → paste a Wikipedia link
GET  /person  → person card (JS fetches data client-side)
POST /watch   → save email + wiki_title
"""

import os, re, logging
from urllib.parse import unquote

log = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.db import init_db, add_watch
from app.email import send_watch_confirmation

app = FastAPI(title="ObituaryWatch", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.on_event("startup")
def startup():
    init_db()

def title_from_url(url: str):
    """Extract (lang, title) from any Wikipedia URL."""
    m = re.search(r"([a-z]{2,3})\.wikipedia\.org/wiki/([^#?&\s]+)", url.strip())
    if not m:
        return None, None
    return m.group(1), m.group(2)

def head(title="ObituaryWatch"):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link href="https://fonts.googleapis.com/css2?family=Special+Elite&family=Courier+Prime:wght@300;400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/style.css">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
.sr-only{{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);border:0}}
.wrap{{max-width:600px;margin:0 auto;padding:60px 24px 100px;position:relative;z-index:1}}
.logo{{width:100px;height:100px;object-fit:contain;display:block;margin:0 auto 18px;filter:drop-shadow(0 0 20px rgba(200,184,154,0.1))}}
.site-name{{font-family:"Special Elite",cursive;font-size:1.9rem;letter-spacing:0.15em;color:#f0ece4;text-transform:uppercase;text-align:center;margin-bottom:5px}}
.site-tagline{{font-size:10px;color:#5a5650;letter-spacing:0.25em;text-transform:uppercase;text-align:center;margin-bottom:52px}}
.label{{font-size:10px;letter-spacing:0.3em;text-transform:uppercase;color:#5a5650;margin-bottom:10px;font-family:"Special Elite",cursive}}
.input{{width:100%;background:#0a0806;border:1px solid #2a2520;color:#e8e4dc;font-family:"Courier Prime",monospace;font-size:14px;padding:13px 20px;border-radius:50px;outline:none;transition:border-color .2s}}
.input:focus{{border-color:#5a5048}}
.input::placeholder{{color:#3a3630}}
.btn{{width:100%;margin-top:10px;background:transparent;border:1px solid #3a3428;color:#7a6a58;font-family:"Courier Prime",monospace;font-size:14px;padding:13px 20px;border-radius:50px;cursor:pointer;transition:all .15s;letter-spacing:0.05em}}
.btn:hover{{border-color:#7a6a58;color:#f0ece4}}
.btn.watch-btn{{border-color:#5a4a38;color:#c8b89a}}
.btn.watch-btn:hover{{border-color:#c8b89a;color:#fff}}
.err{{font-size:12px;color:#7a3a3a;margin-top:10px;font-style:italic;text-align:center;min-height:18px}}
.card{{border:1px solid rgba(255,255,255,0.07);border-radius:18px;padding:26px;background:#000;margin-bottom:16px}}
.person-top{{display:flex;gap:18px;align-items:flex-start;margin-bottom:18px}}
.photo{{width:76px;height:76px;border-radius:50%;object-fit:cover;border:1px solid #2a2520;flex-shrink:0}}
.photo-placeholder{{width:76px;height:76px;border-radius:50%;background:#1a1710;border:1px solid #2a2520;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:700;color:#6a6058;font-family:"Courier Prime",monospace}}
.person-name{{font-size:1.3rem;color:#f0ece4;font-family:"Special Elite",cursive;letter-spacing:0.08em;margin-bottom:4px}}
.person-occ{{font-size:12px;color:#5a5650;letter-spacing:0.05em}}
.info-row{{display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid #0e0e0e;font-size:13px}}
.info-row:last-child{{border-bottom:none}}
.info-key{{color:#5a5650;font-size:10px;letter-spacing:0.1em;text-transform:uppercase}}
.info-val{{color:#b8b0a8}}
.extract{{font-size:12px;color:#4a4a48;line-height:1.75;margin-top:14px;padding-top:14px;border-top:1px solid #0e0e0e}}
.wiki-link{{font-size:11px;color:#3a3630;text-decoration:none;letter-spacing:0.1em;text-transform:uppercase;display:block;text-align:right;margin-top:10px;transition:color .15s}}
.wiki-link:hover{{color:#c8b89a}}
.watch-label{{font-size:10px;letter-spacing:0.25em;text-transform:uppercase;color:#5a5650;font-family:"Special Elite",cursive;margin-bottom:12px}}
.success{{text-align:center;padding:14px;color:#4a7a48;font-size:13px;font-style:italic;display:none}}
.back{{font-size:11px;letter-spacing:0.15em;text-transform:uppercase;color:#3a3630;text-decoration:none;display:inline-flex;align-items:center;gap:5px;margin-bottom:36px;transition:color .15s}}
.back:hover{{color:#f0ece4}}
.skeleton{{background:#0e0e0e;border-radius:4px;animation:pulse 1.5s ease infinite}}
@keyframes pulse{{0%,100%{{opacity:0.5}}50%{{opacity:1}}}}
</style>
</head>
<body>
<div class="wrap">
"""

FOOT = "</div></body></html>"

# ── Home ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(head() + """
<h2 class="sr-only">ObituaryWatch — paste a Wikipedia link to get notified when someone dies</h2>
<img src="/static/logo.png" alt="ObituaryWatch" class="logo">
<div class="site-name">ObituaryWatch</div>
<div class="site-tagline">know before everyone else</div>

<div class="label">Paste a Wikipedia link</div>
<input class="input" id="url" type="url"
  placeholder="https://en.wikipedia.org/wiki/Nicolas_Cage"
  autocomplete="off" spellcheck="false"
  onkeydown="if(event.key==='Enter')go()">
<button class="btn" onclick="go()">look up &rarr;</button>
<div class="err" id="err"></div>

<script>
function go() {
  const v = document.getElementById('url').value.trim();
  const e = document.getElementById('err');
  if (!v) { e.textContent = 'paste a Wikipedia link first.'; return; }
  if (!v.includes('wikipedia.org/wiki/')) {
    e.textContent = "that doesn't look like a Wikipedia link."; return;
  }
  e.textContent = '';
  window.location.href = '/person?url=' + encodeURIComponent(v);
}
</script>
""" + FOOT)

# ── Person card ───────────────────────────────────────────────────────────────

@app.get("/person", response_class=HTMLResponse)
def person_page(url: str = ""):
    if not url:
        return RedirectResponse("/")
    lang, title = title_from_url(url)
    if not title:
        return RedirectResponse("/")
    title = unquote(title)

    # Escape for JS string literals
    safe_title = title.replace("\\", "\\\\").replace("'", "\\'")
    safe_lang  = lang

    return HTMLResponse(head("ObituaryWatch") + f"""
<a class="back" href="/">&#8592; back</a>
<div id="main"></div>

<script>
const TITLE = '{safe_title}';
const LANG  = '{safe_lang}';
</script>
<script src="/static/person.js"></script>
""" + FOOT)

# ── Save watch ────────────────────────────────────────────────────────────────

class WatchReq(BaseModel):
    wiki_title: str
    email:      str
    lang:       str = "en"

@app.post("/watch")
def save_watch(req: WatchReq):
    if not req.email or "@" not in req.email:
        raise HTTPException(400, "Invalid email")
    if not req.wiki_title:
        raise HTTPException(400, "Invalid title")
    full_title = f"{req.lang}:{req.wiki_title.strip()}"
    add_watch(full_title, req.email.strip().lower())
    wiki_url = f"https://{req.lang}.wikipedia.org/wiki/{req.wiki_title}"
    log.info(f"Watch saved: {full_title} for {req.email} — sending confirmation email")
    result = send_watch_confirmation(
        to_email=req.email.strip().lower(),
        person_name=req.wiki_title.replace("_", " "),
        wiki_url=wiki_url,
    )
    log.info(f"Confirmation email result: {result}")
    return {"ok": True}
