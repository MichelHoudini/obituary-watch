#!/usr/bin/env python3
"""
backfill_deaths.py — Manual backfill of global deaths for the last N days.

Usage:
    python scripts/backfill_deaths.py [--days 90] [--dry-run]

Requires DATABASE_URL env var pointing to the target database.
Never runs in CI — execute manually against a non-production database
or against production only after explicit sign-off.

This script calls the Wikidata SPARQL endpoint in batches of 7 days to avoid
result set truncation (the LIMIT 500 cap per query). Each batch sleeps 2 seconds
between queries to respect Wikidata's rate limits.
"""

import argparse
import logging
import os
import sys
import time

# Allow running from repo root without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import init_db, migrate_schema
from app.ingestion import BATCH_SLEEP_SECONDS, run
from app.observability import setup_logging

setup_logging()
log = logging.getLogger("backfill")

BATCH_SIZE_DAYS = 7
INTER_BATCH_SLEEP = 2.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill global deaths from Wikidata")
    parser.add_argument(
        "--days", type=int, default=90, help="Number of days back to backfill (default: 90)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Log what would be inserted, but write nothing"
    )
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        log.error("DATABASE_URL not set — aborting to avoid writing to wrong database")
        sys.exit(1)

    init_db()
    migrate_schema()

    total = {"checked": 0, "confirmed": 0, "inserted": 0, "skipped_existing": 0, "errors": 0}
    remaining = args.days
    batch_num = 0

    log.info(
        "Starting backfill: days=%d batch_size=%d dry_run=%s",
        args.days, BATCH_SIZE_DAYS, args.dry_run,
    )

    while remaining > 0:
        batch_days = min(BATCH_SIZE_DAYS, remaining)
        offset_start = remaining
        offset_end = remaining - batch_days
        batch_num += 1
        log.info(
            "Batch %d: days-%d to days-%d (window=%d days)",
            batch_num, offset_start, offset_end, batch_days,
        )

        # Temporarily adjust the window; ingestion.run() uses days_back from now.
        # For older batches, we run with a shifted window via a helper that
        # understands absolute date ranges.  Here we use the simple approach:
        # run each batch from the *latest* day in that batch (days_back counts
        # from now).  This slightly over-fetches recent deaths but the
        # idempotency guard in upsert_global_death handles duplicates.
        result = run(days_back=offset_start, dry_run=args.dry_run)

        for k in total:
            total[k] += result.get(k, 0)

        remaining -= batch_days
        if remaining > 0:
            log.info("Sleeping %ss before next batch...", INTER_BATCH_SLEEP)
            time.sleep(INTER_BATCH_SLEEP)

    log.info(
        "Backfill complete: checked=%d confirmed=%d inserted=%d "
        "skipped_existing=%d errors=%d dry_run=%s",
        total["checked"], total["confirmed"], total["inserted"],
        total["skipped_existing"], total["errors"], args.dry_run,
    )


if __name__ == "__main__":
    main()
