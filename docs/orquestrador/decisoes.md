# Decisões do Orquestrador — Mortivox

Atualizado: 2026-09-20

## Decisões de ambiente

| Data | Decisão | Motivo | Tipo |
|---|---|---|---|
| 2026-09-20 | Diretório de trabalho: C:\IA (não D:\IA) | D:\ existe como unidade mas está inacessível para escrita (DVD/virtual) | padrão, Michel pode trocar |
| 2026-09-20 | gh CLI instalado via winget 2.101.0 | Não estava disponível no sistema | necessário |
| 2026-09-20 | Banco de teste: SQLite (conftest.py fallback) | Docker não disponível, segundo Supabase não configurado | padrão, Michel pode trocar |

## Decisões de produto (padrão do ORQUESTRADOR.md)

| Data | Decisão | Motivo | Tipo |
|---|---|---|---|
| 2026-09-20 | Critério de região: local da morte (P20) com subida pela hierarquia P131 | Residência (P551) fora do MVP | padrão, Michel pode trocar |
| 2026-09-20 | Toda assinatura por filtro exige pelo menos um filtro | Assinatura sem filtro é inválida | padrão, Michel pode trocar |
| 2026-09-20 | Dado ausente (ocupação ou local sem dados Wikidata) significa "não casa" | Evita falsos positivos por dado faltante | padrão, Michel pode trocar |
| 2026-09-20 | Janela de enriquecimento: ENRICHMENT_GRACE_HOURS=24h | Assinaturas por filtro esperam o enriquecimento Wikidata ou fim da janela | padrão, Michel pode trocar |
| 2026-09-20 | Página pública só exibe morte com data confirmada (sem placeholder) | Evitar expor wikitext bruto | padrão, Michel pode trocar |
| 2026-09-20 | Página de nicho só indexável com >= 5 mortes reais | Evitar conteúdo raso em escala | padrão, Michel pode trocar |

## Decisões de implementação

| Data | Decisão | Motivo | Tipo |
|---|---|---|---|
| 2026-09-21 | `is_confirmed_death()` em `app/dates.py` é a única definição canônica de morte confirmada | Havia 3 implementações divergentes (nicho, email, filtro); unificação elimina inconsistência silenciosa | obrigatório |
| 2026-09-21 | Colunas `occupation_qids`/`location_qids` são `TEXT[]` com índice GIN no Postgres; `TEXT DEFAULT '[]'` JSON no SQLite | Operador `@>` e GIN exigem `TEXT[]`; SQLite não suporta esse tipo | obrigatório |
| 2026-09-21 | `migrate_schema()` chamada no startup do app | Colunas adicionadas via `ALTER TABLE … ADD COLUMN` não estavam sendo criadas em instâncias já existentes | obrigatório |
| 2026-09-21 | Ingestor global desligado por padrão (`INGESTOR_ENABLED`); disparo manual sem essa variável | Evita ingestão acidental em escala antes de validação manual com dry_run | obrigatório |
| 2026-09-21 | Freio de segurança no ingestor: aborta sem gravar se >500 inserções por execução | Spike de dados no Wikidata (e.g. correção em lote) não polui o banco sem revisão humana | obrigatório |
| 2026-09-21 | Ingestor pula títulos já monitorados (`is_already_watched`) | Se ingestor inserir antes do watcher, `record_death` retorna False e o email de watcher nunca é enviado | obrigatório |

## Decisões de teste

| Data | Decisão | Motivo | Tipo |
|---|---|---|---|
| 2026-09-20 | Testes de filtros marcados xfail(strict=True) enquanto filtros AUSENTES | Filtros não implementados; tests escritos contra contrato futuro | obrigatório (ORQUESTRADOR.md) |
| 2026-09-20 | Wikipedia/Wikidata em testes: fixtures JSON versionadas | IPs da Render/GitHub Actions podem ser bloqueados; evitar chamadas reais no CI | obrigatório (ORQUESTRADOR.md) |
| 2026-09-20 | Testes @live fora do CI bloqueante | Chamadas reais à Wikipedia/Wikidata/Resend não podem quebrar CI | obrigatório (ORQUESTRADOR.md) |
| 2026-09-20 | Cobertura mínima: nunca abaixo de 51% (baseline Fase 0); módulos novos >= 90% | Proteção de regressão + qualidade de módulos novos | padrão, Michel pode trocar |
| 2026-09-20 | IDs de teste estáveis: UNI-, INT-, E2E-, ADV-, SEG-, PERF-, EML-, SEO- | Rastreabilidade risco→teste no relatório final | obrigatório (ORQUESTRADOR.md) |
| 2026-09-20 | Profundidade máxima de hierarquia Wikidata: 10 níveis para P279 e P131 | Evita loop infinito em grafos com ciclos; Wikidata tem profundidades típicas < 5 | padrão, Michel pode trocar |
| 2026-09-20 | Conteúdo mínimo para indexação de página de nicho: >= 5 mortes reais listadas | Evita milhares de páginas rasas; configurável em env var | padrão, Michel pode trocar |
| 2026-09-20 | Host canônico: https://mortivox.com/ (apex, sem www) | www e http já redirecionam 301 para este host | confirmado (Fase 0) |
