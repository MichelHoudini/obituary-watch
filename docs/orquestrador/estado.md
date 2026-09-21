# Estado do Orquestrador — Mortivox

Atualizado: 2026-09-20

## Ambiente

| Item | Valor |
|---|---|
| Diretório de trabalho | C:\IA\obituary-watch (D:\ inacessível para escrita) |
| Branch padrão | master |
| Python | 3.14.5 (disponível) |
| Node | disponível |
| Docker | **não encontrado** |
| gh CLI | 2.101.0 instalado via winget, **não autenticado** |
| Postgres local | não disponível |
| Playwright Chromium | instalado (winldd baixado) |
| E2E local | **BLOQUEADO** — WinError 10106 (Winsock) impede uvicorn de subir em subprocess |

**gh auth**: não autenticado. Para ativar PRs via gh, rodar:
```
gh auth login --scopes repo,workflow
```

## Fases

| Fase | Branch | PR | Status | Observações |
|---|---|---|---|---|
| 0. Reconhecimento | qa/f0-reconhecimento | [criar PR](https://github.com/MichelHoudini/obituary-watch/pull/new/qa/f0-reconhecimento) | ENTREGUE | Baseline registrado; gh sem auth, PR manual |
| 1. Plano e contrato | qa/f1-plano | [criar PR](https://github.com/MichelHoudini/obituary-watch/pull/new/qa/f1-plano) | ENTREGUE | Plano, contrato filtros, decisões |
| 2. Unidade e integração | qa/f2-unidade-integracao | [criar PR](https://github.com/MichelHoudini/obituary-watch/pull/new/qa/f2-unidade-integracao) | ENTREGUE | 85 pass, 23 xfail; 54% cov; bug UNI-003b corrigido |
| 3. Sistema (e2e, email, adversarial, perf) | qa/f3-sistema | [criar PR](https://github.com/MichelHoudini/obituary-watch/pull/new/qa/f3-sistema) | ENTREGUE | 126 pass, 36 xfail, 56% cov; bugs EML/ADV documentados via xfail |
| 4. Portão técnico de SEO | qa/f4-seo | — | PENDENTE | — |
| 5. Search Console e indexação | qa/f5-search-console | — | PENDENTE | — |
| 6. Verificação independente e relatório | qa/f6-relatorio | — | PENDENTE | — |

## Pendências humanas (Michel)

- [ ] **gh auth login --scopes repo,workflow** — para push e PRs via CLI
- [ ] **Search Console**: qual o erro exato? Tipo de propriedade (Domínio ou Prefixo de URL)? Método de verificação tentado?
- [ ] **Banco de teste Postgres**: Docker não disponível. Pode instalar Docker Desktop ou criar segundo projeto Supabase de teste?
- [ ] **E2E local BLOQUEADO** — WinError 10106 impede uvicorn em subprocess; testes e2e só rodam no CI (Linux). Não precisa de ação imediata.

## Comandos que funcionam no PowerShell (C:\IA\obituary-watch)

```powershell
# Ativar venv
.\.venv\Scripts\Activate.ps1

# Rodar testes unitários
Set-Location "C:\IA\obituary-watch"
.\.venv\Scripts\python.exe -m pytest tests --ignore=tests/e2e -v

# Cobertura
.\.venv\Scripts\python.exe -m pytest tests --ignore=tests/e2e --cov=app --cov-report=term-missing --cov-branch -q

# Linting
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m vulture app
```

## Achados da Fase 0

### Baseline de testes (versão unit, sem e2e)

| Métrica | Valor |
|---|---|
| Total de testes (unit) | 50 |
| Passou | 50 |
| Falhou | 0 |
| Warnings | 5 (deprecations, não bloqueantes) |
| Tempo total | 12.69s |
| Cobertura total | 51% (linhas + ramos) |

#### Cobertura por módulo

| Módulo | Stmts | Miss | Branch | BrPart | Cover |
|---|---|---|---|---|---|
| app/__init__.py | 0 | 0 | 0 | 0 | 100% |
| app/catalog.py | 30 | 8 | 8 | 0 | 63% |
| app/db.py | 186 | 33 | 30 | 7 | 80% |
| app/email.py | 34 | 23 | 6 | 1 | 30% |
| app/main.py | 237 | 75 | 40 | 4 | 65% |
| app/milestones.py | 66 | 66 | 14 | 0 | 0% |
| app/observability.py | 27 | 1 | 8 | 1 | 94% |
| app/rss.py | 39 | 32 | 8 | 0 | 15% |
| app/seed.py | 9 | 9 | 4 | 0 | 0% |
| app/watcher.py | 113 | 76 | 40 | 1 | 31% |
| app/wiki.py | 50 | 36 | 18 | 0 | 21% |
| **TOTAL** | **791** | **359** | **176** | **14** | **51%** |

#### E2E tests (baseline)
- 8 erros de setup (BLOQUEADO: WinError 10106 Winsock no Windows, uvicorn não sobe em subprocess)
- Falha pré-existente no ambiente local; CI Linux deve funcionar normalmente

### Estrutura de branches e commits recentes (top 10)
- `b4d54ea` Merge PR #17: fix keepalive ping timing out on genuine cold starts
- `32a5204` fix: keepalive ping timing out on genuine cold starts
- `d4e2b89` Merge PR #16: add keepalive ping to prevent Render free-tier 5xx errors
- `0273a08` add: keepalive ping to prevent Render free-tier 5xx errors
- `e17223e` Merge PR #15: distinguish fresh detections from old deaths logged late
- `b774721` Merge PR #14: add Playwright e2e tests
- `9ec79f4` Merge PR #13: add Sentry error tracking + structured JSON logging
- `47058d7` Merge PR #12: add Ruff, mypy, pytest, vulture, CI workflow

### Falhas pré-existentes catalogadas

| ID | Falha | Impacto | Ação |
|---|---|---|---|
| PRE-001 | E2E BLOQUEADO: WinError 10106 Winsock Windows | Local only | Registrado, CI Linux não afetado |
| PRE-002 | 5 warnings de deprecação (on_event, anyio, asyncio) | Zero impacto em runtime | Registrado, não corrigir agora |

### Estrutura de testes existente

```
tests/
  conftest.py          — isolamento SQLite por teste (autouse fixture)
  test_db.py           — 15 testes: watches, deaths, watcher_health
  test_main.py         — 19 testes: format_death_date, detection_label, rotas HTTP
  test_observability.py — 5 testes: logging JSON, Sentry
  test_watcher.py      — 8 testes: extract_death_date, placeholder, edge cases
  e2e/
    conftest.py        — live_server fixture (uvicorn subprocess + Playwright)
    test_e2e.py        — 8 testes: homepage, navigation, person page, JS errors
```

Scripts utilitários relevantes:
- `app/seed.py` — seed do banco para e2e
- `app/watcher.py` — pode ser invocado diretamente para simular morte (tem `if __name__ == "__main__"`)

Migrações: não existem arquivos de migração separados; schema criado por `init_db()` em `db.py` (CREATE IF NOT EXISTS).

### Estado dos filtros: **AUSENTE**

| Critério | Estado |
|---|---|
| Colunas de ancestrais em `deaths` | AUSENTE |
| Campo de filtro em `watches` | AUSENTE |
| Endpoint de escolha de filtro | AUSENTE |
| Enriquecimento Wikidata no watcher | AUSENTE |
| Script de simulação de morte com filtros | AUSENTE |

### Ferramentas disponíveis para banco de teste

| Opção | Estado |
|---|---|
| Docker Postgres | Docker não instalado |
| Postgres local | Não encontrado |
| Segundo projeto Supabase | Não configurado (aguarda Michel) |
| SQLite fallback | DISPONÍVEL — conftest.py usa automaticamente |

Testes de integração que exigem Postgres: marcados como `PENDENTE_DE_BANCO`.

### Sondagem de produção (GET apenas)

| URL | Status | Content-Type | Observações |
|---|---|---|---|
| https://mortivox.com/ | 200 | text/html; charset=utf-8 | TTFB ~5600ms (cold start) |
| https://mortivox.com/robots.txt | 200 | text/plain | Válido, aponta para sitemap.xml |
| https://mortivox.com/sitemap.xml | 200 | application/xml; charset=utf-8 | 113 URLs, XML válido |
| https://mortivox.com/this-page... | 404 | — | 404 real, não soft 404 |
| https://mortivox.com/person/clint-eastwood | 200 | text/html | Tem h1, tem canonical |
| http://mortivox.com/ | 301 | — | Redireciona para https://mortivox.com/ |
| https://www.mortivox.com/ | 301 | — | Redireciona para https://mortivox.com/ |

**Observação TTFB**: ~5600ms indica que o serviço estava dormindo (Render free tier). O keepalive roda a cada 10min mas o GitHub Actions pode atrasar 18-65 min, deixando o serviço adormecer. Isso pode causar 5xx quando o Search Console rastreia.

**Canonical home**: https://mortivox.com/ (correto, um único host canônico)
**HTML sem JS**: conteúdo presente no HTML bruto (não depende de JS para conteúdo principal)

### DNS

| Registro | Valor | Status |
|---|---|---|
| TXT mortivox.com | google-site-verification=xcxPmibax57a7ivhr-gWRk_8wqlEnYlkopHWQEWayYA | presente |
| SPF | — | **AUSENTE** — nenhum registro v=spf1 em mortivox.com |
| DMARC | v=DMARC1; p=none; | presente (política fraca) |
| DKIM (resend._domainkey) | chave RSA presente | presente |

**Crítico para entrega**: SPF ausente pode causar rejeição de email em alguns provedores.

**google-site-verification**: presente no DNS TXT, AUSENTE no HTML (meta tag não injetada pelo servidor). Isso significa:
- Propriedade de Domínio no Search Console: DEVE funcionar (DNS TXT presente)
- Propriedade de Prefixo de URL com meta tag: FALHA (meta tag não está no HTML)

### Workflows CI/CD

| Workflow | Trigger | Jobs |
|---|---|---|
| ci.yml | push master, pull_request | quality (ruff, mypy, vulture, pytest unit) + e2e (playwright chromium) |
| keepalive.yml | cron */10 * * * * | ping /status (curl max-time 90s, retry 1) |
| watcher.yml | schedule (a verificar) | watcher da Wikipedia |
| milestones.yml | schedule seg/qua/sex 10:00 UTC | milestones workflow |

### Achados relevantes para Fases 2-5

1. **email.py**: sem `List-Unsubscribe` / `List-Unsubscribe-Post` (exigido Fase 3)
2. **email.py**: sem link de cancelamento, sem versão texto plano
3. **email.py**: sem dedupe por `(assinante, pessoa, evento)` — só `record_death` tem `ON CONFLICT`
4. **watcher.py**: sem proteção contra race condition (duas execuções simultâneas podem duplicar email em janela pequena)
5. **milestones.py**: 0% de cobertura de testes
6. **rss.py**: 15% de cobertura
5. **TTFB cold start**: ~5600ms — confirmar keepalive está ativo via GitHub Actions
