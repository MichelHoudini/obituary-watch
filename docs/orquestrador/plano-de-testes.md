# Plano de Testes — Mortivox

Arquiteto de testes. Atualizado: 2026-09-20.

## Matriz de risco

Ordem de prioridade fixa, do pior para o menos grave:

| Prioridade | Risco | Impacto | Probabilidade | Superfície |
|---|---|---|---|---|
| P1 | Afirmar falsamente que alguém morreu | CRÍTICO | BAIXA (bug já corrigido) | watcher.py, db.py |
| P2 | Email duplicado por execução concorrente | ALTO | MÉDIA | watcher.py, db.py |
| P2 | Email não enviado por falha do Resend | ALTO | MÉDIA | email.py |
| P3 | Vazamento de dados de assinante | ALTO | BAIXA | main.py, db.py |
| P3 | Token de cancelamento adivinhável ou reutilizável | ALTO | BAIXA | main.py |
| P4 | Match errado dos filtros (falso positivo) | ALTO | ALTA (feature nova) | (futuro) watcher.py, db.py |
| P4 | Match errado dos filtros (falso negativo) | MÉDIO | ALTA (feature nova) | (futuro) watcher.py, db.py |
| P5 | Página pública vazia para o Google (soft 404) | MÉDIO | BAIXA | main.py, wiki.py |
| P6 | TTFB alto / cold start Render | BAIXO | ALTA | render.yaml, keepalive.yml |

---

## Plano de testes com IDs estáveis

### UNI — Testes de unidade

#### Detecção de morte (wikitext)

| ID | Descrição | Risco coberto | Estado |
|---|---|---|---|
| UNI-001 | Placeholder `<!-- {{Death date...}} -->` nunca gera morte detectada | P1 | existente (test_watcher.py) |
| UNI-002 | `{{Death date}}` com parâmetros vazios não detecta | P1 | A CRIAR |
| UNI-003 | `{{Death date}}` com `?` como ano não detecta | P1 | A CRIAR |
| UNI-004 | `{{Death date}}` com ano sem mês e dia não detecta | P1 | A CRIAR |
| UNI-005 | `{{Death date}}` com data futura não detecta | P1 | A CRIAR |
| UNI-006 | Duas datas conflitantes: prevalece a primeira data não-placeholder | P1 | A CRIAR |
| UNI-007 | Real date com comentário trailing ainda detecta | P1 | existente (test_watcher.py) |
| UNI-008 | Template que não é Infobox person é ignorado | P1 | existente (test_watcher.py) |
| UNI-009 | Wikitext malformado não lança exceção (retorna None) | P1 | existente (test_watcher.py) |

#### Formatação de datas

| ID | Descrição | Risco coberto | Estado |
|---|---|---|---|
| UNI-010 | `{{Death date and age|Y|M|D|...}}` formata corretamente | P1/P5 | existente (test_main.py) |
| UNI-011 | `{{Death date|Y|M|D}}` formata sem "and age" | P1/P5 | existente (test_main.py) |
| UNI-012 | Mês inválido (13) retorna valor bruto, não inventa data | P1/P5 | existente (test_main.py) |
| UNI-013 | Precisão de data: só ano — formata sem inventar mês/dia | P1/P5 | A CRIAR |
| UNI-014 | Precisão de data: ano+mês — formata sem inventar dia | P1/P5 | A CRIAR |
| UNI-015 | Placeholder bruto nunca aparece renderizado no HTML | P1/P5 | existente (test_main.py) |
| UNI-016 | `detection_label`: morte fresca = "detected", antiga = "logged" | P1 | existente (test_main.py) |
| UNI-017 | `detection_label`: fronteira em 14 dias (14=detected, 15=logged) | P1 | existente (test_main.py) |

#### i18n / títulos Wikipedia

| ID | Descrição | Risco coberto | Estado |
|---|---|---|---|
| UNI-018 | Título com percent-encoding (acento) resolve para mesmo artigo | P1/P5 | A CRIAR |
| UNI-019 | Título com parênteses percent-encoded resolve corretamente | P1/P5 | A CRIAR |
| UNI-020 | Título com apóstrofo percent-encoded resolve corretamente | P1/P5 | A CRIAR |
| UNI-021 | Título com barra percent-encoded resolve corretamente | P1/P5 | A CRIAR |
| UNI-022 | Subdomínio de idioma (pt, fr, es) produz URL correta | P1/P5 | A CRIAR |
| UNI-023 | Subdomínio de idioma produz texto localizado correto | P1/P5 | A CRIAR |

#### Filtros (contra contrato; `xfail(strict=True)` enquanto AUSENTES)

| ID | Descrição | Risco coberto | Estado |
|---|---|---|---|
| UNI-030 | Hierarquia P131 sempre termina (limite de profundidade) | P4 | A CRIAR (xfail) |
| UNI-031 | Hierarquia P279 não entra em ciclo | P4 | A CRIAR (xfail) |
| UNI-032 | Conjunto de ancestrais contém o valor direto | P4 | A CRIAR (xfail) |
| UNI-033 | Pessoa sem ocupação: array vazio (não null) | P4 | A CRIAR (xfail) |
| UNI-034 | Pessoa sem local: array vazio (não null) | P4 | A CRIAR (xfail) |
| UNI-035 | Pessoa com 10 ocupações: todos os QIDs no array | P4 | A CRIAR (xfail) |
| UNI-036 | Local sem P131: só o próprio QID, sem exceção | P4 | A CRIAR (xfail) |
| UNI-037 | Hypothesis: hierarquia sempre termina para grafo arbitrário | P4 | A CRIAR (xfail) |
| UNI-038 | Hypothesis: match é consistente para entradas aleatórias | P4 | A CRIAR (xfail) |

---

### INT — Testes de integração (banco SQLite/Postgres)

| ID | Descrição | Risco coberto | Estado |
|---|---|---|---|
| INT-001 | Mesma morte detectada 2x → exatamente 1 email por assinante | P2 | A CRIAR |
| INT-002 | Duas execuções simultâneas do watcher não duplicam email | P2 | A CRIAR (PENDENTE_DE_BANCO para concorrência real) |
| INT-003 | Assinante que cancelou entre detecção e envio não recebe | P2/P3 | A CRIAR |
| INT-004 | Falha 5xx do Resend não perde evento, retry não duplica | P2 | A CRIAR |
| INT-005 | Falha timeout do Resend não perde evento | P2 | A CRIAR |
| INT-006 | Falha 429 do Resend não perde evento, não duplica | P2 | A CRIAR |
| INT-007 | Milestone: limiar cruzado uma vez, não repete (watch_milestones) | P2 | A CRIAR |
| INT-008 | Fuso horário UTC: virada de dia não desloca data da morte exibida | P1 | A CRIAR |
| INT-009 | Cancelamento: token de uma assinatura não cancela outra | P3 | A CRIAR |

#### Filtros (xfail enquanto AUSENTES)

| ID | Descrição | Risco coberto | Estado |
|---|---|---|---|
| INT-020 | Contenção de array: "Brooklyn" casa morte em bairro do Brooklyn | P4 | A CRIAR (xfail) |
| INT-021 | "Texas" casa cidade texana | P4 | A CRIAR (xfail) |
| INT-022 | "Músico" casa "cantor de jazz" (hierarquia P279) | P4 | A CRIAR (xfail) |
| INT-023 | "Cantor de jazz" não casa "pianista" (sem sobreposição) | P4 | A CRIAR (xfail) |
| INT-024 | Assinatura só por profissão funciona | P4 | A CRIAR (xfail) |
| INT-025 | Assinatura só por lugar funciona | P4 | A CRIAR (xfail) |
| INT-026 | Assinatura por profissão E lugar funciona | P4 | A CRIAR (xfail) |
| INT-027 | Assinatura sem filtro é rejeitada | P4 | A CRIAR (xfail) |
| INT-028 | Dado ausente não casa | P4 | A CRIAR (xfail) |
| INT-029 | Enriquecimento tardio dentro da janela → passa a casar | P4 | A CRIAR (xfail) |
| INT-030 | Após a janela de enriquecimento, notifica com o que tem | P4 | A CRIAR (xfail) |
| INT-031 | Mesma assinatura por filtro e por pessoa: não gera 2 emails | P2/P4 | A CRIAR (xfail) |

---

### E2E — Testes de sistema (Playwright)

| ID | Descrição | Risco coberto | Estado |
|---|---|---|---|
| E2E-001 | Assinar por pessoa: buscar, escolher, confirmar, cancelar | P2/P3 | existente parcialmente (test_e2e.py) |
| E2E-002 | Email de confirmação recebido (Resend mockado) | P2 | A CRIAR |
| E2E-003 | Cancelamento pelo link do email | P3 | A CRIAR |
| E2E-004 | Mobile (viewport 375px): fluxo completo sem quebra | P5 | A CRIAR |
| E2E-005 | Navegação por teclado (Tab, Enter): fluxo de assinatura | P5 | A CRIAR |
| E2E-006 | Contraste e rótulos: nenhuma violação crítica/séria (axe) | P5 | A CRIAR |
| E2E-007 | Wikipedia fora do ar: mensagem de erro amigável | P5 | A CRIAR |
| E2E-008 | Busca sem resultado: mensagem adequada | P5 | A CRIAR |
| E2E-009 | Email inválido: erro inline sem recarregar página | P3 | A CRIAR |
| E2E-010 | Simular morte: notificação ponta a ponta (script local) | P1/P2 | A CRIAR |
| E2E-011 | @live: busca Wikidata real (fora do CI bloqueante) | P5 | A CRIAR |
| E2E-012 | @live: Resend test addresses (delivered/bounced/complained) | P2 | A CRIAR |

#### Filtros (xfail enquanto AUSENTES)
| ID | Descrição | Risco coberto | Estado |
|---|---|---|---|
| E2E-020 | Assinar por filtro: autocomplete profissão | P4 | A CRIAR (xfail) |
| E2E-021 | Assinar por filtro: autocomplete lugar | P4 | A CRIAR (xfail) |
| E2E-022 | Simular morte com filtro: notificação correta | P4 | A CRIAR (xfail) |

---

### ADV — Testes adversariais

| ID | Descrição | Risco coberto | Estado |
|---|---|---|---|
| ADV-001 | SQL injection em wiki_title: rejeitado sem 500 | P3 | A CRIAR |
| ADV-002 | SQL injection em email: rejeitado sem 500 | P3 | A CRIAR |
| ADV-003 | XSS em nome de pessoa (Wikidata): escapado na página | P3 | A CRIAR |
| ADV-004 | XSS em nome de pessoa: escapado no email | P3 | A CRIAR |
| ADV-005 | Injeção de cabeçalho de email (quebra de linha no campo) | P3 | A CRIAR |
| ADV-006 | Token de cancelamento: aleatório, comprimento >= 32 chars | P3 | A CRIAR |
| ADV-007 | Token de confirmação: uso único (não reutilizável) | P3 | A CRIAR |
| ADV-008 | Token em tempo constante (sem timing oracle) | P3 | A CRIAR |
| ADV-009 | Enumeração: POST /watch não revela se email já existe | P3 | A CRIAR |
| ADV-010 | Rate limit: POST /watch > 5/min rejeita com 429 | P3 | existente (test_main.py) |
| ADV-011 | Rate limit: busca de pessoa com volume alto | P6 | A CRIAR |
| ADV-012 | Unicode estranho em wiki_title: sem 500 | P3 | A CRIAR |
| ADV-013 | Entrada de tamanho absurdo (10k chars): sem 500 | P3 | A CRIAR |

#### Filtros (xfail enquanto AUSENTES)
| ID | Descrição | Risco coberto | Estado |
|---|---|---|---|
| ADV-020 | ID de filtro: regex `^Q[0-9]+$` rejeita inválidos | P4 | A CRIAR (xfail) |
| ADV-021 | `Q1; DROP TABLE` rejeitado sem 500 | P3/P4 | A CRIAR (xfail) |

---

### SEG — Testes de segurança

| ID | Descrição | Risco coberto | Estado |
|---|---|---|---|
| SEG-001 | HSTS presente em respostas HTTPS | P3/P5 | A CRIAR |
| SEG-002 | X-Content-Type-Options: nosniff presente | P3/P5 | A CRIAR |
| SEG-003 | CSP compatível com o que o site já carrega | P3/P5 | A CRIAR |
| SEG-004 | Nenhum segredo em respostas públicas | P3 | A CRIAR |
| SEG-005 | Varredura de segredos no histórico git (trufflehog/gitleaks) | P3 | A CRIAR |

---

### PERF — Testes de performance

| ID | Descrição | Risco coberto | Estado |
|---|---|---|---|
| PERF-001 | Match de 500 mortes contra assinaturas: p95 < 1s | P6 | A CRIAR |
| PERF-002 | Consulta de página de nicho: < 200ms no banco | P6 | A CRIAR |
| PERF-003 | TTFB com cache quente: < 500ms | P6 | A CRIAR |
| PERF-004 | EXPLAIN ANALYZE confirma uso de índice GIN | P6 | A CRIAR (PENDENTE_DE_BANCO para GIN) |

Seed: `tests/perf/seed.py` com 300k mortes e 50k assinaturas.

---

### EML — Testes de email

| ID | Descrição | Risco coberto | Estado |
|---|---|---|---|
| EML-001 | Assunto sem wikitext bruto ou placeholder | P1 | A CRIAR |
| EML-002 | Corpo HTML sem wikitext bruto | P1 | A CRIAR |
| EML-003 | Corpo texto sem placeholder visível | P1 | A CRIAR |
| EML-004 | Link de cancelamento presente e funcional | P3 | A CRIAR |
| EML-005 | List-Unsubscribe header presente | P2/P3 | A CRIAR |
| EML-006 | List-Unsubscribe-Post header presente | P2/P3 | A CRIAR |
| EML-007 | @live: SPF do remetente noreply@mortivox.com | P2 | A CRIAR |
| EML-008 | @live: DKIM do remetente | P2 | A CRIAR |
| EML-009 | @live: DMARC do remetente | P2 | A CRIAR |
| EML-010 | Bounce suprime envios futuros ao endereço | P2 | A CRIAR |
| EML-011 | Reclamação suprime envios futuros | P2 | A CRIAR |

---

### SEO — Testes de SEO técnico

| ID | Descrição | Risco coberto | Estado |
|---|---|---|---|
| SEO-001 | robots.txt: 200, sintaxe válida, não bloqueia indexáveis | P5 | A CRIAR |
| SEO-002 | robots.txt: aponta para sitemap.xml | P5 | existente (test_main.py) |
| SEO-003 | sitemap.xml: 200, application/xml, XML válido | P5 | A CRIAR |
| SEO-004 | sitemap.xml: URLs absolutas do host canônico | P5 | A CRIAR |
| SEO-005 | sitemap.xml: sem URLs com noindex | P5 | A CRIAR |
| SEO-006 | sitemap.xml: máx 50k URLs por arquivo | P5 | A CRIAR |
| SEO-007 | sitemap.xml: todas as URLs respondem 200 e têm canonical para si | P5 | A CRIAR |
| SEO-008 | Variante de host: http→https em um salto | P5 | A CRIAR |
| SEO-009 | Variante de host: www→apex em um salto | P5 | A CRIAR |
| SEO-010 | 404 real (não soft 404 com status 200) | P5 | A CRIAR |
| SEO-011 | Nenhum noindex no HTML ou X-Robots-Tag em página indexável | P5 | A CRIAR |
| SEO-012 | HTML bruto (sem JS) da home contém texto principal, h1, título, meta description | P5 | A CRIAR |
| SEO-013 | HTML bruto de /person/* contém conteúdo real (nome, extract) | P5 | A CRIAR |
| SEO-014 | Sem cloaking: HTML para Googlebot idêntico ao de navegador comum | P5 | A CRIAR |
| SEO-015 | Título único por página | P5 | A CRIAR |
| SEO-016 | Meta description única por página | P5 | A CRIAR |
| SEO-017 | h1 único por página | P5 | A CRIAR |
| SEO-018 | canonical presente e apontando para si mesmo | P5 | A CRIAR |
| SEO-019 | Open Graph e Twitter Card presentes | P5 | A CRIAR |
| SEO-020 | google-site-verification presente no HTML (para propriedade URL Prefix) | P5 | A CRIAR |
| SEO-021 | @live: todas as URLs do sitemap acessíveis e canonicais | P5 | A CRIAR |
| SEO-022 | @live: TTFB quente < 500ms | P6 | A CRIAR |
| SEO-023 | @live: Lighthouse CI — LCP <= 2.5s, CLS < 0.1 | P6 | A CRIAR |

---

## Resumo por estado

| Estado | Quantidade |
|---|---|
| Existente (já temos) | 15 |
| A criar | ~85 |
| A criar (xfail filtros) | ~25 |
| PENDENTE_DE_BANCO | 2 |

## Cobertura mínima exigida

- Nunca abaixo do baseline da Fase 0: 51% total
- Módulos novos: >= 90% linhas e ramos
- Cobertura não substitui mutação dirigida
