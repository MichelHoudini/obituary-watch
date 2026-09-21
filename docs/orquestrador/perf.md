# Performance — Mortivox

Atualizado: 2026-09-21

## Objetivo

Medir o comportamento das consultas críticas com volume realista:
- 300 000 mortes com `occupation_qids TEXT[]` e `location_qids TEXT[]`
- 50 000 assinaturas (60% por pessoa, 20% filtro ocupação, 20% filtro local)

## Como rodar

```powershell
# Localmente com Postgres de teste
$env:DATABASE_URL = "postgresql://mortivox:mortivox@localhost:5432/mortivox_perf"
python tests/perf/seed.py --drop --explain

# Via GitHub Actions (manual)
gh workflow run perf.yml --field deaths_count=300000 --field drop_seed=true
```

## Configuração de Postgres no CI de benchmark

O workflow `perf.yml` usa `postgres:15`. Versão do Supabase de produção: **a confirmar** — ver pendência abaixo.

## Consultas medidas

### `gin_occupation_match`
```sql
SELECT wiki_title FROM deaths
WHERE occupation_qids @> ARRAY['Q177220']::TEXT[]
LIMIT 100
```
Índice esperado: `idx_deaths_occupation_qids` (GIN)

### `nicho_page_query`
```sql
SELECT wiki_title, display_name, death_date, detected_at
FROM deaths
WHERE occupation_qids @> ARRAY['Q177220']::TEXT[]
ORDER BY detected_at DESC
LIMIT 50
```
Índice esperado: GIN + sort por `detected_at`

### `filter_match_combined`
```sql
SELECT email FROM watches
WHERE (filter_occupation_qid IS NOT NULL OR filter_location_qid IS NOT NULL)
  AND (filter_occupation_qid IS NULL
       OR $occ_array::TEXT[] @> ARRAY[filter_occupation_qid]::TEXT[])
  AND (filter_location_qid IS NULL
       OR $loc_array::TEXT[] @> ARRAY[filter_location_qid]::TEXT[])
```
Expectativa: seq scan em watches (tabela pequena, sem GIN necessário).

## Resultados medidos

> **Pendente**: rodar o workflow `perf.yml` com 300k mortes e preencher esta tabela.

| Consulta | Banco | Rows | Índice usado | p50 | p95 | Plano |
|---|---|---|---|---|---|---|
| gin_occupation_match | CI benchmark | 300k | — | — | — | pendente |
| nicho_page_query | CI benchmark | 300k | — | — | — | pendente |
| filter_match_combined | CI benchmark | 50k watches | — | — | — | pendente |

## Planos EXPLAIN ANALYZE

> Preencher após primeira execução do workflow `perf.yml`.

```
-- gin_occupation_match (pendente)
```

```
-- nicho_page_query (pendente)
```

```
-- filter_match_combined (pendente)
```

## Orçamentos alvo (ORQUESTRADOR.md § Fase 3)

| Consulta | Limite | Status |
|---|---|---|
| match de 500 mortes vs. assinaturas (p95) | < 1 s | pendente medição com 300k |
| consulta de página de nicho | < 200 ms | pendente |
| TTFB página pública quente | < 500 ms | @live |

## Notas de investigação

Se o planner escolher `Seq Scan` mesmo com dados suficientes:

1. Verificar se `ANALYZE deaths` foi rodado após o seed (estatísticas podem estar desatualizadas).
2. Verificar `pg_stats` para `occupation_qids`: `SELECT n_distinct, correlation FROM pg_stats WHERE tablename='deaths' AND attname='occupation_qids'`.
3. Antes de forçar com `enable_seqscan=off` em produção, verificar se o índice está sendo usado no PERF-004 (CI com 1k rows + `enable_seqscan=off`).
4. Se a consulta retorna >10% da tabela, o planner pode preferir seq scan mesmo com GIN — nesse caso, refinar o filtro QID para ser mais seletivo.

## Pendências

- [ ] **Michel**: executar `gh workflow run perf.yml` após merge do PR 8 para obter os primeiros números reais.
- [ ] **Michel**: confirmar a versão exata do Postgres no Supabase para alinhar `postgres:15` no perf.yml. Ver pergunta em estado.md.
