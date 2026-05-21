"""
main.py — ObituaryWatch v3.
GET  /        → paste a Wikipedia link
GET  /person  → person card (JS fetches data client-side)
POST /watch   → save email + wiki_title
"""

import os, re, logging
from urllib.parse import unquote

log = logging.getLogger(__name__)

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.db import init_db, add_watch, get_all_watched_titles
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

def fetch_og_data(lang: str, title: str) -> dict:
    """Fetch name, description and image from Wikipedia API for OG tags."""
    try:
        api_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
        r = httpx.get(api_url, timeout=5, follow_redirects=True)
        if r.status_code == 200:
            data = r.json()
            return {
                "name": data.get("title", title.replace("_", " ")),
                "description": data.get("description", ""),
                "extract": data.get("extract", "")[:200],
                "image": data.get("thumbnail", {}).get("source", "https://mortivox.com/static/logo.png"),
            }
    except Exception:
        pass
    return {
        "name": title.replace("_", " "),
        "description": "",
        "extract": "",
        "image": "https://mortivox.com/static/logo.png",
    }

def head(title="Mortivox", og: dict = None):
    og = og or {}
    og_title       = og.get("name", title)
    og_description = og.get("description", "Be notified by email the moment they die.")
    og_image       = og.get("image", "https://mortivox.com/static/logo.png")
    og_url         = og.get("url", "https://mortivox.com")

    if og.get("extract"):
        og_description = og["extract"].rstrip(".") + "..."

    person_title = f"Mortivox — {og_title}" if og.get("name") else "Mortivox"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{person_title}</title>
<meta name="description" content="{og_description}">

<!-- Open Graph -->
<meta property="og:type"        content="website">
<meta property="og:url"
