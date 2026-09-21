# Auditoria de Filtros — Mortivox

Data: 2026-09-21  
Branch base: `feat/paginas-nicho` (commit `bba66e4`)  
Escopo: somente leitura — nenhum código alterado

---

## a) Como a tabela `deaths` é populada hoje

**Fonte única:** apenas mortes de pessoas explicitamente monitoradas chegam à tabela `deaths`.

O watcher (`app/watcher.py`) carrega na inicialização o conjunto `watched` via
`get_all_watched_titles()` (linha 102), que executa:

```sql
SELECT wiki_title FROM monitored_titles
UNION
SELECT wiki_title FROM watches
```

O loop de eventos ignora todo título que não esteja nesse conjunto (linha 136–137):

```python
title = data.get("title", "").replace(" ", "_")
if title not in watched:
    continue
```

Somente ao detectar um `death_date` válido no wikitext o registro entra em `deaths`
(via `record_death()`), e **em seguida** `enrich_death(title)` é chamada
(linha 158) para gravar `occupation_qids` e `location_qids`.

**Consequência:** mortes de pessoas que não estão em `monitored_titles` nem em
`watches` nunca são registradas, mesmo que ocorram no fluxo do Wikipedia
RecentChanges. PR 5 (`feat/ingestao-global`) endereça essa lacuna.

---

## b) INT-003 — caminho de emails e inscrições canceladas

`get_emails_for(wiki_title)` (`app/db.py` linha 286–291) executa:

```sql
SELECT email FROM watches WHERE wiki_title = ?
```

Não há coluna de status de cancelamento. O cancelamento é implementado como
`DELETE` em `remove_watch()` (linha 273–283):

```sql
DELETE FROM watches WHERE wiki_title = ? AND email = ?
```

**Conclusão para INT-003:** inscritos cancelados não aparecem no resultado de
`get_emails_for` porque a linha foi fisicamente removida. O caminho de email
exclui corretamente cancelados. Não existe audit trail de cancelamentos — não há
registro histórico de quem cancelou nem quando.

---

## c) 12 testes marcados como `skip`

| # | Teste | Arquivo | Motivo do skip |
|---|-------|---------|----------------|
| 1 | `test_eml007_spf_record_present` | `test_email_content.py` | `@live`: requer resolução DNS real |
| 2 | `test_eml008_dkim_record_present` | `test_email_content.py` | `@live`: requer resolução DNS real |
| 3 | `test_eml009_dmarc_record_present` | `test_email_content.py` | `@live`: requer resolução DNS real |
| 4 | `test_eml010_bounce_suppresses_future_sends` | `test_email_content.py` | `@live`: requer integração com webhook de bounce do Resend |
| 5 | `test_eml011_complaint_suppresses_future_sends` | `test_email_content.py` | `@live`: requer integração com webhook de complaint do Resend |
| 6 | `test_perf003_warm_ttfb_under_500ms` | `test_performance.py` | `@live`: requer mortivox.com aquecido (Render cold start) |
| 7 | `test_perf004_gin_index_used_for_array_containment` | `test_performance.py` | `DATABASE_URL` ausente em CI → `pytest.skip()` disparado dentro do `xfail`; requer Postgres real com GIN index |
| 8 | `test_seo008_http_redirects_to_https_in_one_hop` | `test_seo.py` | `@live`: redirect HTTP→HTTPS é responsabilidade do proxy Render, não da app |
| 9 | `test_seo009_www_redirects_to_apex_in_one_hop` | `test_seo.py` | `@live`: redirect www→apex é responsabilidade do proxy Render |
| 10 | `test_seo021_live_sitemap_urls_accessible` | `test_seo.py` | `@live`: requer mortivox.com ao vivo |
| 11 | `test_seo022_live_warm_ttfb_under_500ms` | `test_seo.py` | `@live`: requer servidor aquecido |
| 12 | `test_seo023_lighthouse_lcp_cls` | `test_seo.py` | `@live`: requer Lighthouse CLI e servidor ao vivo |

**Padrão de skip nos testes EML-007 a EML-011:** `pytestmark_live = pytest.mark.skipif(True, ...)` definido em `test_email_content.py` linha 253. Aplicado via decorador em cada função.

**Observação sobre PERF-004:** o teste tem `@pytest.mark.xfail(strict=True)` mas invoca `pytest.skip()` internamente quando `DATABASE_URL` não está definido. Em pytest, `pytest.skip()` dentro de um `xfail` resulta em **skipped** (não em xfail), o que explica esse teste aparecer nos 12 skips do CI local.

**Contenção de arrays no CI:** `get_deaths_by_occupation_qid` e `get_deaths_by_location_qid` usam filtragem Python-side via `_decode_qids` (varredura completa da tabela), não operador `@>` do Postgres. PERF-004 testa exatamente a ausência desse caminho otimizado.

---

## d) O que define "morte confirmada"

A definição de morte confirmada **varia por contexto**:

### Páginas de nicho (`/occupation/{qid}`, `/location/{qid}`)

Função `_nicho_death_rows()` em `app/main.py` linha 874:

```python
_comment = re.compile(r"<!--.*?-->", re.DOTALL)
for row in deaths:
    raw = row.get("death_date") or ""
    real = _comment.sub("", raw).strip()
    if real and re.search(r"\d{4}", real):
        confirmed.append(row)
```

Critério: `death_date` não-vazio após remoção de comentários HTML, com pelo
menos um ano de 4 dígitos.

### Email por pessoa específica

Função `extract_death_date()` em `app/watcher.py` linha 65:

- Requer template `{{Infobox ...}}` com campo `death_date`
- Remove comentários HTML
- Se contém `{{Death date...}}`: exige que o **primeiro parâmetro** seja um
  ano de 4 dígitos válido — `{{Death date|?|1|15|...}}` seria rejeitado
- Caso contrário: exige ao menos um `\d{4}` no conteúdo real

Critério mais estrito que o das páginas de nicho — protege contra placeholders
de editor e o falso positivo do Clint Eastwood (2026-07-26).

### Email por filtro de assinatura

`match_watch()` verifica apenas contenção de arrays (`occupation_qids`,
`location_qids`). `should_notify_filter_watch()` verifica apenas a janela de
enriquecimento (`ENRICHMENT_GRACE_HOURS`).

**Não há re-validação da data** no caminho de filtro. O pré-requisito implícito é
que a morte já esteja na tabela `deaths`, o que por sua vez requer que
`extract_death_date()` tenha retornado um valor não-nulo — portanto o critério
estrito do watcher é o guardião. O enriquecimento Wikidata (`enrich_death`)
apenas complementa, não substitui, a confirmação via Wikipedia.

### Resumo comparativo

| Contexto | Critério | Onde |
|----------|----------|------|
| Página nicho | `\d{4}` após strip de comentários HTML | `main.py:_nicho_death_rows` |
| Email por pessoa | `{{Death date\|YYYY\|...}}` com primeiro param válido | `watcher.py:extract_death_date` |
| Email por filtro | Morte em `deaths` (herdada do critério acima) + arrays preenchidos | `filters.py:match_watch` |

---

## e) Migração: arquivo, o que altera, e divergência do contrato

### O que está implementado — `migrate_schema()` em `app/db.py` linha 479

```python
columns = [
    ("watches", "filter_occupation_qid", "TEXT"),
    ("watches", "filter_location_qid",   "TEXT"),
    ("deaths",  "occupation_qids",        "TEXT DEFAULT '[]'"),
    ("deaths",  "location_qids",          "TEXT DEFAULT '[]'"),
]
for table, col, col_def in columns:
    try:
        _exec(conn, f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
    except Exception:
        pass  # coluna já existe — ignora
```

Gera o seguinte SQL (em ordem de aplicação):

```sql
ALTER TABLE watches ADD COLUMN filter_occupation_qid TEXT;
ALTER TABLE watches ADD COLUMN filter_location_qid TEXT;
ALTER TABLE deaths ADD COLUMN occupation_qids TEXT DEFAULT '[]';
ALTER TABLE deaths ADD COLUMN location_qids TEXT DEFAULT '[]';
```

Todas as alterações são **aditivas** (ADD COLUMN) e seguras para rodar antes do
deploy. Erros de coluna duplicada são silenciados, portanto a função é idempotente.

### O que o contrato especificou mas **não está implementado**

`docs/orquestrador/contrato-filtros.md` seção 1 especifica:

```sql
-- Tipo Postgres nativo TEXT[]
ALTER TABLE deaths ADD COLUMN occupation_qids TEXT[] DEFAULT '{}';
ALTER TABLE deaths ADD COLUMN location_qids   TEXT[] DEFAULT '{}';
-- Índices GIN
CREATE INDEX IF NOT EXISTS idx_deaths_occupation_qids ON deaths USING GIN (occupation_qids);
CREATE INDEX IF NOT EXISTS idx_deaths_location_qids   ON deaths USING GIN (location_qids);
```

**Divergências:**

| Ponto | Contrato | Implementação atual |
|-------|----------|---------------------|
| Tipo da coluna | `TEXT[]` (array nativo Postgres) | `TEXT` com JSON serializado |
| Default | `'{}'` (array vazio Postgres) | `'[]'` (JSON vazio) |
| Índices GIN | Criados via `migrate_schema()` | **Ausentes** |
| Contenção de array | Operador `@>` no Postgres | Filtragem Python-side em `_decode_qids` |

**Razão da divergência:** a decisão de usar `TEXT` + JSON em vez de `TEXT[]` foi
tomada para manter compatibilidade com SQLite nos testes (SQLite não tem tipo
nativo de array). Os índices GIN requerem Postgres e `TEXT[]`, portanto também
ficaram fora. `test_perf004` (item 7 acima) documenta exatamente essa lacuna.

**Impacto:** em produção Postgres, a ausência de índices GIN significa varredura
sequencial da tabela `deaths` a cada notificação de filtro. Aceitável enquanto
o volume de mortes for baixo; PR futuro pode adicionar os índices sem alterar o
schema lógico.
