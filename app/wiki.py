"""
wiki.py — Helpers for resolving names → Wikipedia article titles,
and expanding categories via Wikidata SPARQL.

All free, rate-limit-friendly.
"""

import httpx
import logging

log = logging.getLogger(__name__)

WIKI_API      = "https://en.wikipedia.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

# Category → Wikidata occupation Q-codes
CATEGORY_QCODES: dict[str, list[str]] = {
    "actors":      ["Q33999", "Q10800557"],          # actor, film actor
    "musicians":   ["Q639669", "Q177220", "Q488205"], # musician, singer, composer
    "athletes":    ["Q2066131"],                      # athlete
    "politicians": ["Q82955"],                        # politician
    "authors":     ["Q36180", "Q4853732"],            # writer, novelist
    "directors":   ["Q2526255"],                      # film director
    "scientists":  ["Q901", "Q11063"],                # scientist, astronomer
    "artists":     ["Q483501"],                       # artist
}


def search_person(name: str, limit: int = 5) -> list[dict]:
    """
    Search Wikipedia for people matching `name`.
    Returns list of {title, description, url}.
    Uses the opensearch API — very lightweight, no auth needed.
    """
    params = {
        "action": "opensearch",
        "search": name,
        "limit": limit,
        "namespace": 0,
        "format": "json",
    }
    try:
        resp = httpx.get(WIKI_API, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        # opensearch returns [query, [titles], [descriptions], [urls]]
        titles       = data[1]
        descriptions = data[2]
        urls         = data[3]
        return [
            {"title": t.replace(" ", "_"), "display_name": t, "description": d, "url": u}
            for t, d, u in zip(titles, descriptions, urls)
        ]
    except Exception as e:
        log.warning(f"Wikipedia search failed for {name!r}: {e}")
        return []


def resolve_title(name: str) -> str | None:
    """
    Resolve a display name to the canonical Wikipedia article title.
    Returns the underscore_form title, or None if not found.
    """
    results = search_person(name, limit=1)
    return results[0]["title"] if results else None


def get_category_people(category: str, limit: int = 200) -> list[dict]:
    """
    Use Wikidata SPARQL to get Wikipedia article titles for people
    in a given category (e.g. "actors").

    Only returns people who:
    - have an English Wikipedia article
    - are still alive (no death date on Wikidata yet)
    - have a birth date (filters out non-person results)

    Returns list of {wiki_title, display_name}.
    """
    qcodes = CATEGORY_QCODES.get(category.lower())
    if not qcodes:
        log.warning(f"Unknown category: {category!r}")
        return []

    occupation_filter = " ".join(f"wd:{q}" for q in qcodes)

    # SPARQL: people with this occupation, with English Wikipedia article, alive, born
    query = f"""
    SELECT ?item ?itemLabel ?article WHERE {{
      ?item wdt:P106 ?occ .
      VALUES ?occ {{ {occupation_filter} }}
      ?item wdt:P569 ?birth .         # has birth date
      FILTER NOT EXISTS {{ ?item wdt:P570 [] }}  # no death date (still alive per Wikidata)
      ?article schema:about ?item ;
               schema:isPartOf <https://en.wikipedia.org/> .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
    }}
    LIMIT {limit}
    """

    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "ObituaryWatch/1.0 (github.com/yourname/obituary-watch)",
    }
    try:
        resp = httpx.get(
            WIKIDATA_SPARQL,
            params={"query": query},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        bindings = resp.json()["results"]["bindings"]
        results = []
        for b in bindings:
            article_url = b["article"]["value"]
            # Extract title from URL: https://en.wikipedia.org/wiki/Paul_McCartney → Paul_McCartney
            wiki_title = article_url.split("/wiki/")[-1]
            display_name = b["itemLabel"]["value"]
            results.append({"wiki_title": wiki_title, "display_name": display_name})
        return results
    except Exception as e:
        log.warning(f"Wikidata SPARQL failed for category {category!r}: {e}")
        return []
