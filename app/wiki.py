"""
wiki.py — Fetch person info from Wikipedia API.
Just what we need: name, photo, description, birth date, occupation.
"""

import httpx
import re

HEADERS = {"User-Agent": "ObituaryWatch/3.0 (wikipedia-death-monitor)"}

def wiki_api(lang: str = "en") -> str:
    return f"https://{lang}.wikipedia.org/w/api.php"


def title_from_url(url: str) -> str | None:
    """Extract wiki title from a Wikipedia URL."""
    url = url.strip()
    patterns = [
        r"en\.wikipedia\.org/wiki/([^#?&]+)",
        r"wikipedia\.org/wiki/([^#?&]+)",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def get_person_info(wiki_title: str, lang: str = "en") -> dict | None:
    """
    Fetch basic person info from Wikipedia API.
    Returns dict with: title, name, description, extract, thumbnail, url
    or None if not found.
    """
    try:
        resp = httpx.get(
            wiki_api(lang),
            params={
                "action":      "query",
                "titles":      wiki_title.replace("_", " "),
                "prop":        "extracts|pageimages|description",
                "exintro":     True,
                "explaintext": True,
                "pithumbsize": 200,
                "redirects":   True,
                "format":      "json",
            },
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        pages = resp.json()["query"]["pages"]
        page  = next(iter(pages.values()))

        if page.get("missing") is not None:
            return None

        title     = page.get("title", wiki_title.replace("_", " "))
        extract   = page.get("extract", "")
        desc      = page.get("description", "")
        thumbnail = page.get("thumbnail", {}).get("source")

        # Parse birth date from extract
        birth_date = _extract_birth_date(extract)
        birth_year = _extract_birth_year(extract or desc)

        # Parse occupation from description
        occupation = _parse_occupation(desc or extract)

        return {
            "title":       page.get("title", "").replace(" ", "_"),
            "name":        title,
            "description": desc,
            "occupation":  occupation,
            "birth_date":  birth_date,
            "birth_year":  birth_year,
            "extract":     extract[:400] if extract else "",
            "thumbnail":   thumbnail,
            "url":         f"https://{lang}.wikipedia.org/wiki/{wiki_title}",
        }

    except Exception as e:
        return None


def _extract_birth_date(text: str) -> str | None:
    if not text:
        return None
    # Matches: (born January 7, 1964) or (born 7 January 1964)
    m = re.search(
        r"\(born\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{4})",
        text
    )
    return m.group(1) if m else None


def _extract_birth_year(text: str) -> int | None:
    if not text:
        return None
    m = re.search(r"born\s+.*?(\d{4})", text)
    if m:
        return int(m.group(1))
    m = re.search(r"\((\d{4})\)", text)
    if m:
        y = int(m.group(1))
        if 1880 <= y <= 2010:
            return y
    return None


def _parse_occupation(text: str) -> str:
    if not text:
        return ""
    # Priority order — return first match
    occupations = [
        ("Actor",       ["actor", "actress"]),
        ("Musician",    ["musician", "singer", "songwriter", "rapper", "guitarist", "drummer"]),
        ("Director",    ["director", "filmmaker"]),
        ("Writer",      ["writer", "author", "novelist", "poet", "screenwriter"]),
        ("Politician",  ["politician", "president", "prime minister", "senator", "governor"]),
        ("Athlete",     ["athlete", "footballer", "basketball player", "tennis player", "boxer"]),
        ("Scientist",   ["scientist", "physicist", "biologist", "astronomer", "researcher"]),
        ("Artist",      ["artist", "painter", "sculptor", "photographer"]),
        ("Comedian",    ["comedian", "comic"]),
        ("Presenter",   ["presenter", "television host", "tv host", "anchor"]),
        ("Entrepreneur",["entrepreneur", "businessman", "businesswoman", "ceo"]),
        ("Model",       ["model"]),
    ]
    d = text.lower()
    for label, keywords in occupations:
        if any(k in d for k in keywords):
            return label
    # Fallback: capitalize first word(s) before comma
    first = text.split(",")[0].strip()
    return first if len(first) < 35 else ""
