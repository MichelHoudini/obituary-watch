"""
Seed Mortivox with the curated public catalog.

This creates monitored_titles rows only. It does not create fake email
subscribers. The watcher will monitor these pages, and real users can still
subscribe through /watch.
"""

from app.catalog import CATALOG
from app.db import add_watched, init_db

if __name__ == "__main__":
    init_db()
    added = 0
    for person in CATALOG:
        add_watched(
            person["wiki_title"],
            person["display_name"],
            person["category"],
            person.get("birth_year"),
        )
        added += 1
    print(f"Seeded {added} public watch pages.")
