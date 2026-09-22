# Diagnóstico Google Search Console — Mortivox

Elaborado: 2026-09-20

## Resumo executivo

**Problema**: Search Console reportou "site não aceito" ao tentar verificar mortivox.com.

**Causa raiz mais provável**: Cold start do Render free tier. Quando o Search Console
tenta verificar o site, a instância pode estar dormindo e o TTFB supera 5-10 segundos
— fazendo o verificador desistir com timeout ou 5xx.

**Causa secundária**: Escolha do tipo de propriedade. Se Michel tentou "Prefixo de URL"
com verificação por meta tag HTML, isso falha porque a meta tag **não estava no HTML**
(corrigido nesta branch via `GOOGLE_SITE_VERIFICATION` env var).

---

## Análise técnica

### 1. Cold start (CRÍTICO)

| Dado | Valor |
|---|---|
| TTFB cold start observado (Fase 0) | ~5.600ms |
| Limite típico do verificador Google | ~5.000ms |
| Keepalive GitHub Actions | programado a cada 10min, atrasa 18-65min |

**O verificador do Google abandona a requisição se não receber resposta antes do timeout.**
Uma instância adormecida no Render free tier leva até 10s para acordar — fora do limite.

**Solução**: Verificar o site enquanto a instância está quente (dentro de 10min após
qualquer acesso). Para eliminar o problema permanentemente, o keepalive no GitHub Actions
precisa ser mais confiável (cron `*/5 * * * *` em vez de `*/10`).

### 2. Meta tag `google-site-verification` ausente no HTML (CORRIGIDO NESTA BRANCH)

| Método de verificação | Funciona? |
|---|---|
| DNS TXT (Propriedade de Domínio) | ✅ SIM — registro `xcxPmibax57a7ivhr-gWRk_8wqlEnYlkopHWQEWayYA` presente |
| Meta tag HTML (Propriedade de Prefixo de URL) | ✅ CORRIGIDO — via `GOOGLE_SITE_VERIFICATION` env var |

**Antes desta branch**, a meta tag `<meta name="google-site-verification" content="...">` 
não era injetada no HTML. Isso bloqueava a verificação pelo método "Prefixo de URL".

**Depois desta branch**, se a env var `GOOGLE_SITE_VERIFICATION` estiver configurada no
Render, a meta tag aparece em todas as páginas.

### 3. SPF ausente (risco de email, não bloqueia Search Console)

O domínio mortivox.com tem DKIM e DMARC mas **sem registro SPF**. Não impede a
verificação do Search Console, mas pode causar rejeição de emails de notificação.

---

## Passo a passo para verificar no Search Console

### Opção A: Propriedade de Domínio (recomendada — funciona sem meta tag)

1. Acesse https://search.google.com/search-console
2. Clique em **Adicionar propriedade** → escolha **Domínio**
3. Digite: `mortivox.com`
4. O Search Console mostrará um registro TXT para adicionar ao DNS
5. **O registro já existe**: `google-site-verification=xcxPmibax57a7ivhr-gWRk_8wqlEnYlkopHWQEWayYA`
6. Se o registro que o Search Console pedir for diferente do que está no DNS: substituir o antigo
7. Clique em **Verificar**

### Opção B: Propriedade de Prefixo de URL (requer meta tag)

1. Primeiro, configure a env var no Render:
   - Acesse o dashboard do Render → serviço `mortivox` → **Environment**
   - Adicione: `GOOGLE_SITE_VERIFICATION` = token do Search Console
   - (O token está na tela do Search Console, método "Tag HTML", campo `content="..."`)
2. Reinicie o serviço (ou aguarde redeploy)
3. Verifique que `https://mortivox.com/` contém a meta tag (Ctrl+U no browser, buscar "google-site-verification")
4. Acesse https://search.google.com/search-console → **Adicionar propriedade** → **Prefixo de URL**
5. Digite: `https://mortivox.com/`
6. Escolha verificação por **Tag HTML**
7. **IMPORTANTE**: Fazer a verificação enquanto o Render está acordado — acesse o site primeiro

---

## Envio do sitemap

Após verificação bem-sucedida:

1. No Search Console, selecione a propriedade `mortivox.com`
2. Menu esquerdo: **Sitemaps**
3. Em "Adicionar novo sitemap", insira: `sitemap.xml`
4. Clique em **Enviar**

O sitemap em https://mortivox.com/sitemap.xml tem 113 URLs (catálogo completo).

---

## URLs prioritárias para "Solicitar indexação"

Ordem de prioridade (impacto SEO maior → menor):

| # | URL | Motivo de prioridade |
|---|---|---|
| 1 | `https://mortivox.com/` | Página inicial — maior tráfego esperado |
| 2 | `https://mortivox.com/people` | Diretório público — linkado da home |
| 3 | `https://mortivox.com/person/clint-eastwood` | Maior volume de buscas esperado |
| 4 | `https://mortivox.com/person/dolly-parton` | Alta notoriedade |
| 5 | `https://mortivox.com/person/mick-jagger` | Alta notoriedade |
| 6 | `https://mortivox.com/person/willie-nelson` | Alta notoriedade |
| 7 | `https://mortivox.com/person/paul-mccartney` | Alta notoriedade |
| 8 | `https://mortivox.com/lists/actors` | Página de lista — SEO agregado |
| 9 | `https://mortivox.com/lists/musicians` | Página de lista — SEO agregado |
| 10 | `https://mortivox.com/deaths` | Feed público de mortes detectadas |

Para solicitar indexação: Search Console → **Inspecionar URL** → cole a URL → **Solicitar indexação**.

---

## Monitoramento pós-verificação

Após verificação e envio do sitemap, aguardar 48-72h e verificar:

1. **Cobertura** (Search Console → Cobertura): URLs do sitemap devem aparecer
2. **Erros de rastreamento**: Verificar se há erros 5xx (cold start)
3. **Melhorias**: Verificar alertas de Core Web Vitals ou dados estruturados

Se aparecerem erros 5xx: problema de cold start confirmado. Solução: 
- Upgrade do plano Render (elimina sleep)
- Ou tornar o keepalive mais confiável (cron `*/5`)

---

## Pendências de Michel

- [ ] Confirmar qual tipo de propriedade tentou (Domínio ou Prefixo de URL)
- [ ] Configurar `GOOGLE_SITE_VERIFICATION` no Render (se usar Prefixo de URL)
- [ ] Verificar no Search Console **enquanto o site está acordado**
- [ ] Enviar sitemap após verificação
- [ ] Adicionar SPF ao DNS: `v=spf1 include:spf.resend.com ~all`
