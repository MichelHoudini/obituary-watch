# Relatório Final — Mortivox QA

Gerado: 2026-09-20  
Revisor: Orquestrador (independente de subagente)

---

## 1. Números: baseline vs. final

| Métrica | Fase 0 (baseline) | Fase 6 (final) | Δ |
|---|---|---|---|
| Testes passando | 50 | 173 | +123 |
| xfail (bugs documentados / features pendentes) | 0 | 36 | +36 |
| Skipped (@live, @perf) | 0 | 12 | +12 |
| Cobertura total | 51% | 62% | +11 pp |
| Cobertura app/main.py | 65% | 86% | +21 pp |
| Cobertura app/catalog.py | 63% | 84% | +21 pp |
| Cobertura app/db.py | 80% | 80% | = |
| Cobertura app/email.py | 30% | 55% | +25 pp |
| Tempo de suíte (unit, sem e2e) | 12.69s | ~111s | + (mais testes) |
| Bugs de produto corrigidos | — | 1 (UNI-003b) | — |
| Bugs documentados em xfail (feature pendente) | — | 36 | — |

**Estabilidade** (3 execuções consecutivas):

| Execução | Passou | Skipped | xfailed |
|---|---|---|---|
| 1 | 173 | 12 | 36 |
| 2 | 173 | 12 | 36 |
| 3 | 173 | 12 | 36 |

Nenhum teste flaky detectado.

---

## 2. Matriz de risco × cobertura de testes

| Prioridade | Risco | Testes que cobrem | Veredicto |
|---|---|---|---|
| **P1** | Afirmar falsamente que alguém morreu | UNI-001 a UNI-023 (test_detection_regression.py), UNI-003b corrigido | **COBERTO** — o teste UNI-003b prova que o bug de `?` como ano foi corrigido. Testes de regressão passariam a falhar se o bug voltasse. |
| **P2** | Email duplicado por execução concorrente | INT-001 (idempotência), INT-002 (race condition) | **COBERTO para o caso sequencial** — INT-001 prova idempotência via `ON CONFLICT`. INT-002 usa `threading` com SQLite (não Postgres); prova que o mecanismo de lock funciona, mas concorrência real no Postgres não está coberta (bloqueada por falta de Docker/Supabase de teste). |
| **P2** | Email não enviado por falha do Resend | EML-001, EML-007 a EML-011 (fixture `capture_resend`) | **PARCIALMENTE COBERTO** — a fixture captura a chamada HTTP ao Resend, mas retry em falha 5xx/429 não está implementado nem testado (INT-004 a INT-006 não foram escritos). |
| **P3** | Vazamento de dados de assinante | SEG-004, SEG-005 | **COBERTO** — SEG-004 verifica que respostas públicas não contêm padrões de chaves; SEG-005 varre arquivos git por padrão de token. |
| **P3** | Token de cancelamento adivinhável ou reutilizável | ADV-006 a ADV-008 (xfail) | **NÃO IMPLEMENTADO** — tokens de cancelamento não existem. Testes ADV-006/007/008 são xfail `strict=True` e falhariam se a feature fosse adicionada incorretamente. |
| **P4** | Match errado dos filtros (falso positivo/negativo) | UNI-030 a UNI-038, INT-020 a INT-031 (todos xfail) | **PENDENTE** — filtros completamente ausentes (`app/filters.py` não existe). 20 contratos de teste escritos, todos xfail `strict=True`. |
| **P5** | Página pública vazia para o Google | SEO-001 a SEO-019 (45 testes), SEO-020 (2 testes) | **COBERTO** — robots.txt, sitemap, canonical, OG, Twitter Card, conteúdo no HTML bruto, Googlebot idêntico ao browser. |
| **P6** | TTFB alto / cold start | PERF-001 (match performance) | **PARCIALMENTE COBERTO** — match performance cobre P95 < 1s com 50 registros. PERF-003 (TTFB de página com cache quente) é @live e fica fora do CI. |

---

## 3. Bugs de produto encontrados

### 3.1 Corrigido: UNI-003b — `?` como ano bypassa proteção de data

**Branch**: `qa/f2-unidade-integracao`  
**Arquivo**: `app/watcher.py`  
**Teste de prova**: `test_uni003b_question_mark_mixed` em `test_detection_regression.py`

`extract_death_date()` detectava morte em artigos com `{{Death date|?|...}}` porque a regex verificava a presença do template mas não exigia que o primeiro parâmetro fosse um ano válido (`\d{4}`). Um artigo contendo `{{Death date|?|1|1}}` (placeholder de ano) seria incorretamente marcado como morte confirmada.

**Correção**: adicionado `\s*\d{4}\b` como requisito no primeiro parâmetro do template.

### 3.2 Aberto em xfail: EML-002 — data de morte em wikitext bruto no email

**Arquivo**: `app/email.py` — corpo HTML usa f-string com `death_date` diretamente, sem passar por `format_death_date()`.  
**Teste**: `test_eml002_html_body_has_no_raw_wikitext_template` (xfail strict).  
**Impacto**: emails podem exibir `{{Death date|2024|1|1}}` literalmente para o assinante.

### 3.3 Aberto em xfail: ADV-004 — XSS no nome de pessoa no email

**Arquivo**: `app/email.py` — `person_name` inserido no template HTML sem `html.escape()`.  
**Teste**: `test_adv004_xss_person_name_escaped_in_email` (xfail strict).  
**Impacto**: nome de pessoa com `<script>` ou aspas pode injetar HTML no email.

### 3.4 Aberto em xfail: INT-003 — assinante cancelado recebe email

**Arquivo**: `app/watcher.py` / `app/db.py` — não há verificação de status de cancelamento antes do envio.  
**Teste**: `test_int003_cancelled_subscriber_does_not_receive` (xfail strict).  
**Impacto**: após cancelar, assinante ainda pode receber notificações.

### 3.5 Aberto em xfail: EML-003/004/005/006 — email sem versão texto, sem link de cancelamento, sem List-Unsubscribe

**Arquivo**: `app/email.py`  
**Impacto**: email pode ser classificado como spam por provedores que exigem `List-Unsubscribe`.

### 3.6 Aberto em xfail: SEG-001/002/003 — cabeçalhos de segurança (HSTS, X-Content-Type-Options, CSP)

**Observação**: esses cabeçalhos são configurados pela Render, não pelo FastAPI. Os testes verificam o app diretamente (sem Render na frente), por isso falham. A Render free tier injeta HSTS e `X-Content-Type-Options` em produção. Risco real é baixo.

---

## 4. Análise de qualidade dos testes (revisão independente)

### 4.1 Testes que testam o produto, não o código

Os testes com maior risco de serem "tautológicos" (testam implementação em vez de comportamento) foram revisados:

| Teste | Veredicto |
|---|---|
| `test_uni001_placeholder_comment_not_detected` | **VÁLIDO** — injeta wikitext real, verifica que None é retornado. Falharia se o regex fosse removido. |
| `test_int001_idempotency_same_death_sends_one_email` | **VÁLIDO** — chama `add_watch()` + `record_death()` duas vezes e verifica count. Falharia sem `ON CONFLICT`. |
| `test_seo011_no_noindex_on_indexable_pages` | **VÁLIDO** — corrigido durante Fase 4 (era tautológico, foi reescrito para testar os primeiros 3000 chars do HTML). |
| `test_seg004_no_secrets_in_public_responses` | **VÁLIDO** — verifica regex contra respostas reais. Falharia se RESEND_API_KEY vazasse em JSON de erro. |
| `test_seg005_no_secrets_in_git_tracked_files` | **VÁLIDO** — padrão tightened para excluir snake_case (evita falso positivo em variáveis de código). |
| `test_perf001_match_performance_acceptable` | **VÁLIDO** — mede tempo real de execução com 50 registros. Falharia se o match regredir para O(n²). |

**Nenhum teste vazio (que passa por qualquer razão) foi encontrado** nos testes não-xfail.

### 4.2 xfails `strict=True`: proteção correta

Todos os 36 xfails usam `strict=True`, o que significa que se a funcionalidade for implementada mas o teste não for removido, o CI falha. Isso força o desenvolvedor a revisar o contrato dos filtros quando a feature for entregue.

### 4.3 Limites do INT-002 (race condition com SQLite)

`test_int002_concurrent_watcher_no_duplicate_email` usa `threading.Thread` com SQLite em modo WAL. SQLite com WAL é single-writer, então o lock é garantido pelo banco. Quando migrar para Postgres com pool de conexões real, esse teste precisa ser reescrito com `multiprocessing` ou dois processos FastAPI reais. **Risco residual: médio.**

---

## 5. Resultados @live e performance

| Teste | Resultado | Observação |
|---|---|---|
| PERF-001 (match 500 mortes × 50 watches) | P95 < 1s (**PASSOU**) | Medido com SQLite; Postgres com GIN seria mais rápido |
| PERF-004 (GIN index) | **xfail** | Requer Postgres; Docker não disponível |
| SEO-021 (live sitemap) | **SKIPPED** | @live, somente quando `TEST_LIVE=1` |
| SEO-022 (TTFB < 500ms) | **SKIPPED** | @live; TTFB observado na Fase 0: ~5600ms (cold start) |
| SEO-023 (Lighthouse LCP/CLS) | **SKIPPED** | @live; Lighthouse não instalado localmente |

---

## 6. Estado do Search Console

| Item | Status |
|---|---|
| DNS TXT `google-site-verification` | **PRESENTE** em mortivox.com |
| Meta tag `<meta name="google-site-verification">` no HTML | **CORRIGIDO** nesta branch (env var `GOOGLE_SITE_VERIFICATION`) |
| Propriedade de Domínio verificável | **SIM** — registro DNS presente |
| Sitemap enviado | **AGUARDANDO MICHEL** — pronto para envio após verificação |
| Páginas indexadas | Não verificado (Search Console não acessível ao agente) |
| Diagnóstico detalhado | `docs/orquestrador/search-console.md` |

**Causa provável do "site não aceito"**: cold start da Render (TTFB ~5600ms) + meta tag ausente no HTML. Ambos corrigidos (meta tag na branch; cold start mitigado pelo keepalive em `keepalive.yml`).

---

## 7. O que ficou BLOQUEADO e por quê

| Item | Causa | Desbloqueio |
|---|---|---|
| INT-004/005/006 — retry do Resend | Não implementado no código de produto (`app/email.py` não tem retry) | Implementar retry em `email.py` |
| INT-009 — token de uma assinatura não cancela outra | Tokens de cancelamento não implementados | Implementar tokens de cancelamento |
| ADV-006/007/008 — tokens de segurança | Tokens não implementados | Idem |
| EML-004 — link de cancelamento | Não implementado | Idem |
| PERF-004 — índice GIN | Docker não disponível no ambiente | Michel instalar Docker Desktop ou criar Supabase de teste |
| E2E local | WinError 10106 (Winsock) no Windows | Rodar em CI Linux (já funciona) |
| Filtros por profissão e região (P4 inteiro) | `app/filters.py` não existe | Implementar filtros |

---

## 8. Riscos residuais (por ordem de gravidade)

1. **EML-002 + ADV-004**: wikitext bruto e XSS no email. Risco direto para usuários reais. Correção de ~15 linhas em `app/email.py`. Alta prioridade.

2. **INT-003**: assinante cancelado pode receber email. Simples de corrigir: adicionar verificação de `cancelled_at IS NULL` na query de assinaturas ativas.

3. **EML-005/006**: ausência de `List-Unsubscribe`. Provedores de email (Gmail, Outlook) podem marcar como spam. Correção: 2 linhas de cabeçalho no `email.py`.

4. **INT-002 (race condition Postgres)**: teste usa SQLite. Quando houver Postgres, refatorar para garantir que `ON CONFLICT DO NOTHING` é atômico com o `INSERT INTO deaths`.

5. **TTFB cold start**: keepalive roda a cada 10min, GitHub Actions pode atrasar até 65min. Reduzir cron para `*/5` elimina o risco para o Search Console.

6. **SPF ausente**: domínio mortivox.com sem `v=spf1`. Correção: adicionar `v=spf1 include:spf.resend.com ~all` no DNS do Spaceship.

---

## 9. Próximas ações (ordenadas por impacto)

| # | Ação | Responsável | Esforço |
|---|---|---|---|
| 1 | Corrigir EML-002: chamar `format_death_date()` no corpo do email | Dev | ~5 linhas |
| 2 | Corrigir ADV-004: `html.escape(person_name)` em `app/email.py` | Dev | ~1 linha |
| 3 | Corrigir INT-003: filtrar `cancelled_at IS NULL` em `get_watches_for_person()` | Dev | ~2 linhas |
| 4 | Adicionar `List-Unsubscribe` e `List-Unsubscribe-Post` ao email | Dev | ~5 linhas |
| 5 | Verificar propriedade no Search Console (Opção A: Domínio via DNS TXT) | **Michel** | 5 min |
| 6 | Enviar sitemap no Search Console após verificação | **Michel** | 2 min |
| 7 | Adicionar SPF ao DNS: `v=spf1 include:spf.resend.com ~all` | **Michel** | 2 min |
| 8 | Reduzir keepalive de `*/10` para `*/5` em `keepalive.yml` | Dev | 1 linha |
| 9 | Implementar tokens de cancelamento (ADV-006/007/008, EML-004) | Dev | ~50 linhas |
| 10 | Configurar `GOOGLE_SITE_VERIFICATION` no Render (após merge desta branch) | **Michel** | Render dashboard |
| 11 | Merge da branch `qa/f5-search-console` (contém a fix da meta tag) | **Michel** | aprovação de PR |
| 12 | Implementar filtros por profissão e região (20 contratos de teste prontos) | Dev | sprint completa |

---

## 10. Checklist de integridade (produção somente leitura)

- [x] Nenhuma escrita no Supabase de produção
- [x] Nenhum email enviado a assinante real
- [x] Nenhum dado apagado
- [x] Nenhuma alteração de DNS realizada
- [x] Nenhuma remoção de URL solicitada no Search Console
- [x] Nenhuma mudança em `robots.txt` que bloqueia caminhos
- [x] Nenhum segredo impresso em log, PR ou relatório
- [x] Nenhum merge realizado (aguardando Michel)
