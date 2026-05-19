"""
main.py — ObituaryWatch v3. Three routes only.
GET  /        → paste a Wikipedia link
GET  /person  → person card (data fetched client-side to avoid 403s)
POST /watch   → save email + wiki_title
"""

import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import re

from app.db import init_db, add_watch

app = FastAPI(title="ObituaryWatch", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.on_event("startup")
def startup():
    init_db()

def title_from_url(url: str):
    url = url.strip()
    m = re.search(r"wikipedia\.org/wiki/([^#?&\s]+)", url)
    return m.group(1) if m else None

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
  if (!v.includes('wikipedia.org/wiki/')) { e.textContent = "that doesn't look like a Wikipedia link."; return; }
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
    title = title_from_url(url)
    if not title:
        return RedirectResponse("/")

    safe_title = title.replace("'", "\\'").replace('"', '')

    return HTMLResponse(head("ObituaryWatch — loading...") + f"""
<a class="back" href="/">&#8592; back</a>
<div id="main"></div>

<script>
const TITLE = '{safe_title}';
const YEAR  = new Date().getFullYear();

const OCCS = [
  ['Actor',        ['actor','actress']],
  ['Musician',     ['musician','singer','songwriter','rapper','composer','guitarist']],
  ['Director',     ['director','filmmaker']],
  ['Writer',       ['writer','author','novelist','poet','screenwriter','journalist']],
  ['Politician',   ['politician','president','prime minister','senator','governor']],
  ['Athlete',      ['athlete','footballer','basketball player','tennis player','boxer']],
  ['Scientist',    ['scientist','physicist','biologist','astronomer','mathematician']],
  ['Artist',       ['artist','painter','sculptor','photographer']],
  ['Comedian',     ['comedian','comic']],
  ['Entrepreneur', ['entrepreneur','businessman','businesswoman','ceo']],
  ['Model',        ['model']],
];

function occ(desc) {{
  if (!desc) return '';
  const d = desc.toLowerCase();
  for (const [l,ks] of OCCS) if (ks.some(k=>d.includes(k))) return l;
  return desc.split(/[,.(]/)[0].trim().slice(0,30);
}}

function birthDate(text) {{
  if (!text) return null;
  const m = text.match(/\\(born\\s+([A-Za-z]+\\s+\\d{{1,2}},?\\s+\\d{{4}}|\\d{{1,2}}\\s+[A-Za-z]+\\s+\\d{{4}}|\\d{{4}})/i);
  return m ? m[1] : null;
}}

function birthYear(text) {{
  if (!text) return null;
  const m = text.match(/born.*?(\\d{{4}})/i);
  return m ? parseInt(m[1]) : null;
}}

// Show skeleton while loading
document.getElementById('main').innerHTML = `
  <div class="card">
    <div class="person-top">
      <div class="photo-placeholder skeleton" style="border:none"></div>
      <div style="flex:1;padding-top:6px">
        <div class="skeleton" style="height:20px;width:55%;margin-bottom:10px;border-radius:10px"></div>
        <div class="skeleton" style="height:13px;width:35%;border-radius:6px"></div>
      </div>
    </div>
    <div class="skeleton" style="height:13px;margin-bottom:8px;border-radius:6px"></div>
    <div class="skeleton" style="height:13px;width:70%;border-radius:6px"></div>
  </div>`;

async function load() {{
  try {{
    const url = 'https://en.wikipedia.org/w/api.php?action=query' +
      '&titles=' + encodeURIComponent(TITLE.replace(/_/g,' ')) +
      '&prop=extracts|pageimages|description' +
      '&exintro=true&explaintext=true&pithumbsize=200&redirects=true' +
      '&format=json&origin=*';
    const data  = await (await fetch(url)).json();
    const page  = Object.values(data.query.pages)[0];

    if (page.missing !== undefined) {{
      document.getElementById('main').innerHTML =
        '<div style="text-align:center;color:#5a5650;padding:60px 0;font-style:italic">Page not found on Wikipedia.</div>';
      return;
    }}

    const name    = page.title || TITLE.replace(/_/g,' ');
    const desc    = page.description || '';
    const extract = (page.extract || '').slice(0,320);
    const thumb   = page.thumbnail?.source || '';
    const job     = occ(desc);
    const bd      = birthDate(extract);
    const by      = birthYear(extract);
    const age     = by ? YEAR - by : null;

    document.title = name + ' — ObituaryWatch';

    const photo = thumb
      ? `<img src="${{thumb}}" alt="${{name}}" class="photo">`
      : `<div class="photo-placeholder">${{name.charAt(0).toUpperCase()}}</div>`;

    let rows = '';
    if (job) rows += `<div class="info-row"><span class="info-key">Occupation</span><span class="info-val">${{job}}</span></div>`;
    if (bd)  rows += `<div class="info-row"><span class="info-key">Born</span><span class="info-val">${{bd}}${{age?' &middot; age '+age:''}}</span></div>`;
    else if (age) rows += `<div class="info-row"><span class="info-key">Age</span><span class="info-val">${{age}}</span></div>`;

    const safeN = name.replace(/'/g,"\\'");
    const first = name.split(' ')[0];

    document.getElementById('main').innerHTML = `
      <div class="card">
        <div class="person-top">
          ${{photo}}
          <div>
            <div class="person-name">${{name}}</div>
            <div class="person-occ">${{desc}}</div>
          </div>
        </div>
        ${{rows}}
        ${{extract ? '<div class="extract">'+extract+'...</div>' : ''}}
        <a class="wiki-link" href="https://en.wikipedia.org/wiki/${{TITLE}}" target="_blank">view on Wikipedia &rarr;</a>
      </div>
      <div class="card">
        <div class="watch-label">Get notified when ${{first}} dies</div>
        <input class="input" id="email" type="email" placeholder="your@email.com"
          onkeydown="if(event.key==='Enter')doWatch('${{safeN}}')">
        <button class="btn watch-btn" onclick="doWatch('${{safeN}}')">Watch</button>
        <div class="err" id="err"></div>
        <div class="success" id="ok">&#10003; You're watching ${{name}}. We'll email you when Wikipedia registers their death.</div>
      </div>`;

  }} catch(e) {{
    console.error(e);
    document.getElementById('main').innerHTML =
      '<div style="text-align:center;color:#5a5650;padding:60px 0;font-style:italic">Error loading. Please try again.</div>';
  }}
}}

async function doWatch(name) {{
  const email = document.getElementById('email').value.trim();
  const err   = document.getElementById('err');
  if (!email || !email.includes('@')) {{ err.textContent = 'enter a valid email.'; return; }}
  err.textContent = '';
  const r = await fetch('/watch', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{wiki_title: TITLE, email}})
  }});
  if (r.ok) {{
    document.getElementById('email').style.display = 'none';
    document.querySelector('.watch-btn').style.display = 'none';
    document.getElementById('ok').style.display = 'block';
  }} else {{
    err.textContent = 'something went wrong. try again.';
  }}
}}

load();
</script>
""" + FOOT)

# ── Save watch ────────────────────────────────────────────────────────────────

class WatchReq(BaseModel):
    wiki_title: str
    email:      str

@app.post("/watch")
def save_watch(req: WatchReq):
    if not req.email or "@" not in req.email:
        raise HTTPException(400, "Invalid email")
    if not req.wiki_title:
        raise HTTPException(400, "Invalid title")
    add_watch(req.wiki_title.strip(), req.email.strip().lower())
    return {"ok": True}
