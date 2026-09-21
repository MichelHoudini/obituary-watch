"""
Seed de performance: 300k mortes + 50k assinaturas para PERF-001.

Uso:
  python -m tests.perf.seed [--deaths 300000] [--watches 50000]

Cria o banco no diretório atual (SQLite) ou usa DATABASE_URL (Postgres).
NUNCA conecta à produção — DATABASE_URL de teste deve ser separado.
"""
import argparse
import sys
import time
from pathlib import Path

# Adiciona o repo root ao path se executado diretamente
_repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_repo_root))


def seed(n_deaths: int = 300_000, n_watches: int = 50_000) -> None:
    from app.db import init_db

    init_db()

    import sqlite3
    conn = sqlite3.connect("obituary_watch.db")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    print(f"Inserindo {n_deaths:,} mortes...")
    t0 = time.perf_counter()
    conn.executemany(
        "INSERT OR IGNORE INTO deaths (wiki_title, display_name, death_date) VALUES (?, ?, ?)",
        (
            (f"Perf_Death_{i}", f"Perf Death {i}", "{{Death date and age|2026|1|1|1930|1|1}}")
            for i in range(n_deaths)
        ),
    )
    conn.commit()
    print(f"  Mortes: {time.perf_counter() - t0:.1f}s")

    print(f"Inserindo {n_watches:,} assinaturas...")
    t1 = time.perf_counter()
    n_people = min(n_watches, 10_000)
    conn.executemany(
        "INSERT OR IGNORE INTO watches (wiki_title, email) VALUES (?, ?)",
        (
            (f"Perf_Death_{i % n_people}", f"fan{i}@perf.example.com")
            for i in range(n_watches)
        ),
    )
    conn.commit()
    conn.close()
    print(f"  Assinaturas: {time.perf_counter() - t1:.1f}s")
    print(f"Seed completo em {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed de performance para Mortivox")
    parser.add_argument("--deaths", type=int, default=300_000)
    parser.add_argument("--watches", type=int, default=50_000)
    args = parser.parse_args()
    seed(args.deaths, args.watches)
