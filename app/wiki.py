"""
wiki.py — Search and category helpers.
Simple, fast, reliable.
"""

import re
import httpx
import logging

log = logging.getLogger(__name__)

WIKI_API        = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API    = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
HEADERS         = {"User-Agent": "ObituaryWatch/2.0 (wikipedia-death-monitor)"}

CATEGORY_QCODES: dict[str, list[str]] = {
    "actors":      ["Q33999", "Q10800557"],
    "musicians":   ["Q639669", "Q177220", "Q488205"],
    "athletes":    ["Q2066131"],
    "politicians": ["Q82955"],
    "authors":     ["Q36180", "Q4853732"],
    "directors":   ["Q2526255"],
    "scientists":  ["Q901", "Q11063"],
    "artists":     ["Q483501"],
}


def _extract_birth_year(text: str) -> int | None:
    if not text:
        return None
    for pattern in [r'born\s+(\d{4})', r'\((\d{4})[\u2013\-]', r'\b(19\d{2}|20[01]\d)\b']:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            y = int(m.group(1))
            if 1880 <= y <= 2010:
                return y
    return None


def search_person(name: str, limit: int = 6) -> list[dict]:
    """
    Search is now done client-side via Wikipedia API with origin=*.
    This endpoint is kept for compatibility but returns empty.
    The frontend calls Wikipedia directly to avoid server-side 403s.
    """
    return []


def _wikidata_search(name: str, limit: int) -> list[dict]:
    """
    Wikidata search — returns rich descriptions like 'American actor, born 1964'.
    Resolves Wikipedia article titles in the same call via sitelinks.
    """
    try:
        # Search for entities
        resp = httpx.get(
            WIKIDATA_API,
            params={
                "action":   "wbsearchentities",
                "search":   name,
                "language": "en",
                "uselang":  "en",
                "type":     "item",
                "limit":    min(limit * 3, 15),
                "format":   "json",
            },
            headers=HEADERS,
            timeout=8,
        )
        resp.raise_for_status()
        items = resp.json().get("search", [])
        if not items:
            return []

        # Get entity IDs and fetch Wikipedia sitelinks in one batch call
        entity_ids = [item["id"] for item in items if item.get("id")]
        sitelinks  = _fetch_sitelinks(entity_ids)

        results = []
        seen    = set()
        for item in items:
            label = item.get("label", "").strip()
            desc  = item.get("description", "").strip()
            eid   = item.get("id", "")

            if not label or label.lower() in seen:
                continue

            wiki_title = sitelinks.get(eid)
            if not wiki_title:
                continue  # no English Wikipedia article → skip

            seen.add(label.lower())

            # Clean up description
            if len(desc) > 80:
                desc = desc[:77] + "..."
            if desc:
                desc = desc[0].upper() + desc[1:]

            results.append({
                "title":        wiki_title,
                "display_name": label,
                "description":  desc,
                "birth_year":   _extract_birth_year(desc),
                "url":          f"https://en.wikipedia.org/wiki/{wiki_title}",
            })

            if len(results) >= limit:
                break

        return results

    except Exception as e:
        log.warning(f"Wikidata search failed for {name!r}: {e}")
        return []


def _fetch_sitelinks(entity_ids: list[str]) -> dict[str, str]:
    """Batch fetch Wikipedia article titles for Wikidata entity IDs."""
    if not entity_ids:
        return {}
    try:
        resp = httpx.get(
            WIKIDATA_API,
            params={
                "action":     "wbgetentities",
                "ids":        "|".join(entity_ids),
                "props":      "sitelinks",
                "sitefilter": "enwiki",
                "format":     "json",
            },
            headers=HEADERS,
            timeout=8,
        )
        resp.raise_for_status()
        out = {}
        for eid, entity in resp.json().get("entities", {}).items():
            title = entity.get("sitelinks", {}).get("enwiki", {}).get("title", "")
            if title:
                out[eid] = title.replace(" ", "_")
        return out
    except Exception as e:
        log.warning(f"Sitelinks fetch failed: {e}")
        return {}


def _wikipedia_opensearch(name: str, limit: int) -> list[dict]:
    """Fallback: Wikipedia opensearch. Fast but no descriptions."""
    try:
        resp = httpx.get(
            WIKI_API,
            params={
                "action":    "opensearch",
                "search":    name,
                "limit":     limit,
                "namespace": 0,
                "format":    "json",
            },
            headers=HEADERS,
            timeout=8,
        )
        resp.raise_for_status()
        _, titles, descs, urls = resp.json()
        return [
            {
                "title":        t.replace(" ", "_"),
                "display_name": t,
                "description":  d or "",
                "birth_year":   _extract_birth_year(d or ""),
                "url":          u,
            }
            for t, d, u in zip(titles, descs, urls)
        ]
    except Exception as e:
        log.warning(f"Wikipedia opensearch failed for {name!r}: {e}")
        return []


def resolve_title(name: str) -> str | None:
    results = search_person(name, limit=1)
    return results[0]["title"] if results else None


def get_category_people(category: str, limit: int = 200) -> list[dict]:
    """Wikidata SPARQL: living people in a category with English Wikipedia articles."""
    qcodes = CATEGORY_QCODES.get(category.lower())
    if not qcodes:
        return []

    occupation_filter = " ".join(f"wd:{q}" for q in qcodes)
    query = f"""
    SELECT ?item ?itemLabel ?article WHERE {{
      ?item wdt:P106 ?occ .
      VALUES ?occ {{ {occupation_filter} }}
      ?item wdt:P569 ?birth .
      FILTER NOT EXISTS {{ ?item wdt:P570 [] }}
      ?article schema:about ?item ;
               schema:isPartOf <https://en.wikipedia.org/> .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
    }}
    LIMIT {limit}
    """
    try:
        resp = httpx.get(
            WIKIDATA_SPARQL,
            params={"query": query},
            headers={"Accept": "application/sparql-results+json", **HEADERS},
            timeout=30,
        )
        resp.raise_for_status()
        return [
            {
                "wiki_title":   b["article"]["value"].split("/wiki/")[-1],
                "display_name": b["itemLabel"]["value"],
            }
            for b in resp.json()["results"]["bindings"]
        ]
    except Exception as e:
        log.warning(f"SPARQL failed for {category!r}: {e}")
        return []
