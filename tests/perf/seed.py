"""
Seed de performance: 300 000 mortes + 50 000 assinaturas para testes PERF.

Uso:
  DATABASE_URL=postgresql://... python tests/perf/seed.py [--drop] [--explain]
  DATABASE_URL=postgresql://... python tests/perf/seed.py --only deaths
  DATABASE_URL=postgresql://... python tests/perf/seed.py --deaths-count 10000

Insere dados sintéticos com occupation_qids e location_qids como TEXT[] para
exercitar o índice GIN.  Fallback SQLite disponível para testes locais sem
Postgres, mas sem arrays (SQLite usa JSON TEXT).

ATENÇÃO: Never apontar DATABASE_URL para o banco de produção.
"""
import argparse
import logging
import os
import sys
import time
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_repo_root))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("perf_seed")

DEATHS_COUNT  = 300_000
WATCHES_COUNT = 50_000
BATCH_SIZE    = 2_000

OCC_POOL = [
    "Q177220", "Q36180", "Q82955", "Q33999", "Q1028181",
    "Q2865819", "Q49757", "Q11900058", "Q639669", "Q158852",
]
LOC_POOL = [
    "Q60", "Q142", "Q30", "Q21", "Q183",
    "Q145", "Q1297", "Q65", "Q16", "Q38",
]


def _occ_array_pg(i: int) -> str:
    a = OCC_POOL[i % len(OCC_POOL)]
    b = OCC_POOL[(i + 3) % len(OCC_POOL)]
    return "{" + a + "," + b + "}"


def _loc_array_pg(i: int) -> str:
    a = LOC_POOL[i % len(LOC_POOL)]
    b = LOC_POOL[(i + 4) % len(LOC_POOL)]
    return "{" + a + "," + b + "}"


def _seed_postgres(db_url: str, n_deaths: int, n_watches: int, drop: bool, explain: bool,
                   only: str | None) -> None:
    import psycopg2

    if "supabase" in db_url.lower() or "mortivox.com" in db_url.lower():
        log.error("DATABASE_URL looks like production — aborting.")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor()

    if only in (None, "deaths"):
        if drop:
            log.info("Dropping existing seed deaths…")
            cur.execute("DELETE FROM deaths WHERE wiki_title LIKE 'perf_seed_%'")
            conn.commit()

        log.info("Seeding %d deaths (Postgres, batch=%d)…", n_deaths, BATCH_SIZE)
        t0 = time.perf_counter()
        for batch_start in range(0, n_deaths, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, n_deaths)
            rows = [
                (
                    f"perf_seed_{i}",
                    f"Perf Seed {i}",
                    f"{{{{Death date|2026|{(i % 12) + 1:02d}|{(i % 28) + 1:02d}}}}}",
                    _occ_array_pg(i),
                    _loc_array_pg(i),
                )
                for i in range(batch_start, batch_end)
            ]
            cur.executemany(
                "INSERT INTO deaths (wiki_title, display_name, death_date, "
                "  occupation_qids, location_qids) "
                "VALUES (%s, %s, %s, %s::TEXT[], %s::TEXT[]) "
                "ON CONFLICT (wiki_title) DO NOTHING",
                rows,
            )
            conn.commit()
            if (batch_end % 50_000 == 0) or batch_end == n_deaths:
                log.info("  deaths %d/%d (%.1fs)", batch_end, n_deaths, time.perf_counter() - t0)
        log.info("Deaths done: %.1fs", time.perf_counter() - t0)

    if only in (None, "watches"):
        if drop:
            log.info("Dropping existing seed watches…")
            cur.execute("DELETE FROM watches WHERE email LIKE '%@perf.example.com'")
            conn.commit()

        log.info("Seeding %d watches (Postgres)…", n_watches)
        person_count = int(n_watches * 0.60)
        occ_count    = int(n_watches * 0.20)
        loc_count    = n_watches - person_count - occ_count
        t1 = time.perf_counter()

        for batch_start in range(0, person_count, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, person_count)
            cur.executemany(
                "INSERT INTO watches (wiki_title, email, filter_occupation_qid, filter_location_qid) "
                "VALUES (%s, %s, NULL, NULL) ON CONFLICT DO NOTHING",
                [(f"perf_seed_{i % n_deaths}", f"wp_{i}@perf.example.com")
                 for i in range(batch_start, batch_end)],
            )
            conn.commit()

        for batch_start in range(0, occ_count, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, occ_count)
            cur.executemany(
                "INSERT INTO watches (wiki_title, email, filter_occupation_qid, filter_location_qid) "
                "VALUES ('', %s, %s, NULL) ON CONFLICT DO NOTHING",
                [(f"wo_{i}@perf.example.com", OCC_POOL[i % len(OCC_POOL)])
                 for i in range(batch_start, batch_end)],
            )
            conn.commit()

        for batch_start in range(0, loc_count, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, loc_count)
            cur.executemany(
                "INSERT INTO watches (wiki_title, email, filter_occupation_qid, filter_location_qid) "
                "VALUES ('', %s, NULL, %s) ON CONFLICT DO NOTHING",
                [(f"wl_{i}@perf.example.com", LOC_POOL[i % len(LOC_POOL)])
                 for i in range(batch_start, batch_end)],
            )
            conn.commit()

        log.info("Watches done: %.1fs", time.perf_counter() - t1)

    if explain:
        _run_explain(cur)

    conn.close()


def _run_explain(cur: object) -> None:
    queries = {
        "gin_occupation_match": (
            "EXPLAIN (ANALYZE, BUFFERS) "
            "SELECT wiki_title FROM deaths "
            "WHERE occupation_qids @> ARRAY['Q177220']::TEXT[] LIMIT 100"
        ),
        "gin_location_match": (
            "EXPLAIN (ANALYZE, BUFFERS) "
            "SELECT wiki_title FROM deaths "
            "WHERE location_qids @> ARRAY['Q60']::TEXT[] LIMIT 100"
        ),
        "nicho_page_query": (
            "EXPLAIN (ANALYZE, BUFFERS) "
            "SELECT wiki_title, display_name, death_date, detected_at "
            "FROM deaths WHERE occupation_qids @> ARRAY['Q177220']::TEXT[] "
            "ORDER BY detected_at DESC LIMIT 50"
        ),
        "filter_match_combined": (
            "EXPLAIN (ANALYZE, BUFFERS) "
            "SELECT email FROM watches "
            "WHERE (filter_occupation_qid IS NOT NULL OR filter_location_qid IS NOT NULL) "
            "  AND (filter_occupation_qid IS NULL "
            "       OR ARRAY['Q177220','Q36180']::TEXT[] @> ARRAY[filter_occupation_qid]::TEXT[]) "
            "  AND (filter_location_qid IS NULL "
            "       OR ARRAY['Q60','Q30']::TEXT[] @> ARRAY[filter_location_qid]::TEXT[])"
        ),
    }
    for name, sql in queries.items():
        log.info("=== EXPLAIN ANALYZE: %s ===", name)
        cur.execute(sql)
        plan = "\n".join(r[0] for r in cur.fetchall())
        print(plan)
        log.info("=== end %s ===\n", name)


def _seed_sqlite(n_deaths: int, n_watches: int) -> None:
    """Fallback: SQLite seed (no TEXT[] arrays, limited perf value)."""
    import sqlite3

    from app.db import init_db
    init_db()
    conn = sqlite3.connect("obituary_watch.db")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    log.info("Seeding %d deaths (SQLite)…", n_deaths)
    t0 = time.perf_counter()
    conn.executemany(
        "INSERT OR IGNORE INTO deaths (wiki_title, display_name, death_date) VALUES (?, ?, ?)",
        ((f"perf_seed_{i}", f"Perf Seed {i}", "{{Death date|2026|01|01}}") for i in range(n_deaths)),
    )
    conn.commit()
    log.info("Seeding %d watches (SQLite)…", n_watches)
    conn.executemany(
        "INSERT OR IGNORE INTO watches (wiki_title, email) VALUES (?, ?)",
        ((f"perf_seed_{i % min(n_watches, 10_000)}", f"fan{i}@perf.example.com")
         for i in range(n_watches)),
    )
    conn.commit()
    conn.close()
    log.info("SQLite seed done: %.1fs", time.perf_counter() - t0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed performance test data for Mortivox")
    parser.add_argument("--deaths-count", type=int, default=DEATHS_COUNT)
    parser.add_argument("--watches-count", type=int, default=WATCHES_COUNT)
    parser.add_argument("--drop", action="store_true",
                        help="Delete existing seed rows before inserting")
    parser.add_argument("--only", choices=["deaths", "watches"], default=None)
    parser.add_argument("--explain", action="store_true",
                        help="Run EXPLAIN ANALYZE after seeding (Postgres only)")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        _seed_postgres(db_url, args.deaths_count, args.watches_count,
                       args.drop, args.explain, args.only)
    else:
        log.warning("DATABASE_URL not set — falling back to SQLite (no GIN arrays).")
        _seed_sqlite(args.deaths_count, args.watches_count)

    log.info("Seed complete.")


if __name__ == "__main__":
    main()
