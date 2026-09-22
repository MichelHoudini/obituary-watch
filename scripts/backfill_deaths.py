#!/usr/bin/env python3
"""
backfill_deaths.py — Backfill de mortes globais para os últimos N dias.

Uso:
    python scripts/backfill_deaths.py [--days 90] [--batch-days 7]
                                      [--batch-wiki-calls 50]
                                      [--state-file PATH]
                                      [--resume-from YYYY-MM-DD]
                                      [--dry-run]

Funcionalidades:
- Janelas não sobrepostas (from_date → to_date por lote), evitando SPARQL
  redundante ao contrário do approach anterior que usava days_back crescente.
- Estado persistido em JSON: se o script for interrompido, relançar com
  --state-file e a mesma --state-file retoma do ponto onde parou.
- Limites por lote: --batch-wiki-calls cap de chamadas Wikipedia por janela.
- --dry-run: mostra o que faria sem escrever nada e sem salvar estado.

Requer DATABASE_URL. Nunca deve ser executado contra o banco de produção
sem aprovação explícita do Michel.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import init_db, migrate_schema
from app.ingestion import run_window
from app.observability import setup_logging

setup_logging()
log = logging.getLogger("backfill")

DEFAULT_STATE_FILE = Path.home() / ".mortivox_backfill_state.json"
DEFAULT_BATCH_DAYS = 7
DEFAULT_BATCH_WIKI_CALLS = 50
INTER_BATCH_SLEEP = 3.0


def _load_state(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:
        log.warning("Could not load state file %s: %s", path, exc)
        return None


def _save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _date_from_str(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _build_batches(total_days: int, batch_days: int) -> list[tuple[date, date]]:
    """Return non-overlapping (from_date, to_date) pairs, oldest-first.

    Example for total_days=10, batch_days=3:
      [(day-10, day-7), (day-7, day-4), (day-4, day-1), (day-1, today+1)]
    """
    today = datetime.now(UTC).date()
    batches: list[tuple[date, date]] = []
    remaining = total_days
    while remaining > 0:
        batch = min(batch_days, remaining)
        to_d   = today - timedelta(days=remaining - batch)
        from_d = today - timedelta(days=remaining)
        batches.append((from_d, to_d))
        remaining -= batch
    return batches


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill global deaths from Wikidata")
    parser.add_argument("--days", type=int, default=90, help="Total days to backfill (default: 90)")
    parser.add_argument("--batch-days", type=int, default=DEFAULT_BATCH_DAYS,
                        help="SPARQL window size per batch in days (default: 7)")
    parser.add_argument("--batch-wiki-calls", type=int, default=DEFAULT_BATCH_WIKI_CALLS,
                        help="Max Wikipedia calls per batch (default: 50)")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE,
                        help="JSON file for resume state (default: ~/.mortivox_backfill_state.json)")
    parser.add_argument("--resume-from", type=str, default=None,
                        help="Override resume point: skip batches before YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true",
                        help="Evaluate without writing; state file not updated")
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        log.error("DATABASE_URL not set — aborting to avoid writing to wrong database")
        sys.exit(1)

    init_db()
    migrate_schema()

    batches = _build_batches(args.days, args.batch_days)

    # Determine resume point
    resume_from: date | None = None
    existing_state = _load_state(args.state_file) if not args.dry_run else None

    if args.resume_from:
        resume_from = _date_from_str(args.resume_from)
        log.info("Resuming from --resume-from %s", resume_from)
    elif existing_state:
        completed = existing_state.get("last_completed_to")
        if completed:
            resume_from = _date_from_str(completed)
            log.info("Resuming from state file: last_completed_to=%s", completed)

    # Totals (carry over from previous run if resuming)
    totals: dict = existing_state.get("totals", {
        "checked": 0, "confirmed": 0, "inserted": 0,
        "skipped_existing": 0, "errors": 0,
    }) if existing_state else {
        "checked": 0, "confirmed": 0, "inserted": 0,
        "skipped_existing": 0, "errors": 0,
    }

    log.info(
        "Starting backfill: days=%d batch_days=%d batch_wiki_calls=%d "
        "batches=%d dry_run=%s resume_from=%s",
        args.days, args.batch_days, args.batch_wiki_calls,
        len(batches), args.dry_run, resume_from,
    )

    processed = 0
    for i, (from_d, to_d) in enumerate(batches, 1):
        if resume_from and from_d < resume_from:
            log.info("Batch %d/%d [%s → %s]: SKIP (already completed)", i, len(batches), from_d, to_d)
            continue

        log.info("Batch %d/%d [%s → %s]", i, len(batches), from_d, to_d)

        from_dt = datetime(from_d.year, from_d.month, from_d.day, tzinfo=UTC)
        to_dt   = datetime(to_d.year,   to_d.month,   to_d.day,   tzinfo=UTC)

        result = run_window(
            from_dt=from_dt,
            to_dt=to_dt,
            max_wikipedia_calls=args.batch_wiki_calls,
            dry_run=args.dry_run,
        )

        if result.get("aborted"):
            log.error("Batch %d aborted (safety brake). Stopping backfill.", i)
            sys.exit(2)

        for k in totals:
            totals[k] += result.get(k, 0)

        processed += 1

        if not args.dry_run:
            state = {
                "started_at": existing_state.get("started_at", datetime.now(UTC).isoformat())
                              if existing_state else datetime.now(UTC).isoformat(),
                "args": {"days": args.days, "batch_days": args.batch_days,
                         "batch_wiki_calls": args.batch_wiki_calls},
                "batches_total": len(batches),
                "batches_completed": i,
                "last_completed_to": to_d.isoformat(),
                "totals": totals,
            }
            _save_state(args.state_file, state)

        if i < len(batches):
            log.info("Sleeping %ss before next batch...", INTER_BATCH_SLEEP)
            time.sleep(INTER_BATCH_SLEEP)

    log.info(
        "Backfill %s: batches=%d/%d checked=%d confirmed=%d inserted=%d "
        "skipped_existing=%d errors=%d",
        "DRY-RUN complete" if args.dry_run else "complete",
        processed, len(batches),
        totals["checked"], totals["confirmed"], totals["inserted"],
        totals["skipped_existing"], totals["errors"],
    )

    if not args.dry_run and processed == len(batches):
        log.info("All batches complete. Removing state file %s", args.state_file)
        try:
            args.state_file.unlink(missing_ok=True)
        except Exception as exc:
            log.warning("Could not remove state file: %s", exc)


if __name__ == "__main__":
    main()
