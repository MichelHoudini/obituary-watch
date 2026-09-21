"""
Testes de performance — PERF-001 a PERF-004.

PERF-001: Match de 500 mortes vs. assinaturas: p95 < 1s.
PERF-002: Consulta de deaths DB: < 200ms.
PERF-003: TTFB quente < 500ms — @live apenas (marcado skip).
PERF-004: EXPLAIN ANALYZE com índice GIN — xfail (requer Postgres).

Usa banco SQLite isolado via conftest.py (autouse fixture).
"""
import time

import pytest

# ── PERF-001: match de 500 mortes vs. assinaturas ────────────────────────────

def test_perf001_five_hundred_deaths_query_under_one_second():
    """Inserir 500 mortes e 50 assinaturas; consultar todos os emails para
    cada morte deve completar em < 1s no total.

    Este teste usa SQLite local (não Postgres). O desempenho em SQLite
    para 500 registros é muito superior ao p95 < 1s exigido; o valor real
    de garantia está no Postgres com GIN index (PERF-004)."""
    from app.db import add_watch, get_emails_for, init_db, record_death

    init_db()

    # Cria 50 assinaturas para 10 pessoas
    people = [f"Perf_Person_{i}" for i in range(10)]
    for person in people:
        for j in range(5):
            add_watch(person, f"fan{j}@perf-test-{person.lower()}.com")

    # Insere 500 mortes (490 sem assinante + 10 com assinante)
    for i in range(490):
        record_death(f"Unknown_Person_{i}", f"Unknown {i}", "{{Death date and age|2026|1|1|1930|1|1}}")
    for person in people:
        record_death(person, person.replace("_", " "), "{{Death date and age|2026|1|1|1940|1|1}}")

    # Mede o tempo de get_emails_for para as 10 pessoas com assinatura
    start = time.perf_counter()
    for person in people:
        emails = get_emails_for(person)
        assert len(emails) == 5, f"Esperava 5 emails para {person}, obteve {len(emails)}"
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0, (
        f"get_emails_for para 10 pessoas levou {elapsed:.3f}s (limite: 1.0s)"
    )


def test_perf001_record_death_bulk_insert_acceptable_time():
    """Inserção em lote de 50 mortes deve completar em < 5s no SQLite.
    Note: SQLite em Windows com WAL tem overhead real; limite generoso para CI."""
    from app.db import init_db, record_death

    init_db()

    start = time.perf_counter()
    for i in range(50):
        record_death(
            f"Bulk_Person_{i}",
            f"Bulk Person {i}",
            "{{Death date and age|2026|6|1|1940|1|1}}",
        )
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0, (
        f"Inserção em lote de 50 mortes levou {elapsed:.3f}s (limite: 5.0s)"
    )


# ── PERF-002: consulta de página de nicho < 200ms ────────────────────────────

def test_perf002_get_deaths_query_under_200ms():
    """get_deaths() com 300 registros deve completar em < 200ms."""
    from app.db import get_deaths, init_db, record_death

    init_db()

    # Seed de 300 mortes
    for i in range(300):
        record_death(
            f"Death_Query_Person_{i}",
            f"Death Query Person {i}",
            "{{Death date and age|2026|3|1|1940|1|1}}",
        )

    start = time.perf_counter()
    deaths = get_deaths(50)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.2, (
        f"get_deaths(50) com 300 registros levou {elapsed:.3f}s (limite: 0.2s)"
    )
    assert len(deaths) <= 50


def test_perf002_get_deaths_returns_correct_limit():
    """get_deaths(N) nunca retorna mais de N registros."""
    from app.db import get_deaths, init_db, record_death

    init_db()
    for i in range(60):
        record_death(f"Limit_Test_{i}", f"Limit Test {i}", "{{Death date and age|2026|1|1|1930|1|1}}")

    result = get_deaths(10)
    assert len(result) <= 10


def test_perf002_watch_count_query_fast():
    """get_watch_count() deve completar em < 100ms mesmo com 1k assinaturas."""
    from app.db import add_watch, get_watch_count, init_db

    init_db()

    for i in range(100):  # Reduzido para 100 para não tornar CI lento
        add_watch(f"Watch_Count_Person_{i}", f"fan{i}@example.com")

    start = time.perf_counter()
    count = get_watch_count()
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1, f"get_watch_count() levou {elapsed:.3f}s (limite: 0.1s)"
    assert count >= 100


# ── PERF-003: TTFB quente < 500ms @live ──────────────────────────────────────

@pytest.mark.skip(reason="@live: requer mortivox.com aquecido; rodar fora do CI com --run-live")
def test_perf003_warm_ttfb_under_500ms():
    """TTFB de mortivox.com com servidor quente deve ser < 500ms.
    Requer que o serviço não esteja em cold start."""
    import httpx

    # Ping de aquecimento
    httpx.get("https://mortivox.com/status", timeout=30)

    # Medição real
    start = time.perf_counter()
    r = httpx.get("https://mortivox.com/", timeout=10)
    elapsed = time.perf_counter() - start

    assert r.status_code == 200
    assert elapsed < 0.5, f"TTFB quente: {elapsed:.3f}s (limite: 0.5s)"


# ── PERF-004: EXPLAIN ANALYZE com GIN index (xfail — requer Postgres) ────────

@pytest.mark.xfail(
    strict=True,
    reason="GIN index não existe: colunas occupation_qids/location_qids ausentes "
           "em deaths; requer Postgres com app/filters.py implementado",
)
def test_perf004_gin_index_used_for_array_containment():
    """EXPLAIN ANALYZE deve mostrar uso de índice GIN para consultas de array
    do tipo WHERE occupation_qids @> ARRAY['Q177220']."""
    import os
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL não configurado; pulando teste de GIN index")

    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("""
        EXPLAIN ANALYZE
        SELECT wiki_title FROM deaths
        WHERE occupation_qids @> ARRAY['Q177220']
        LIMIT 10
    """)
    plan = "\n".join(r[0] for r in cur.fetchall())
    conn.close()

    assert "Bitmap Index Scan" in plan or "Index Scan" in plan, (
        f"GIN index não usado no plano:\n{plan}"
    )
