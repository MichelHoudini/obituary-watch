# Contrato de Filtros — Mortivox

Arquiteto de testes. Atualizado: 2026-09-20.
Estado atual dos filtros: **AUSENTE**. Este contrato define o que os testes vão afirmar. Os testes de filtros são escritos contra este contrato e marcados `xfail(strict=True)` com razão "filtros pendentes" até a implementação chegar.

---

## 1. Tabelas e colunas

### Tabela `deaths` (acréscimos necessários)

```sql
ALTER TABLE deaths ADD COLUMN occupation_qids TEXT[] DEFAULT '{}';
ALTER TABLE deaths ADD COLUMN location_qids   TEXT[] DEFAULT '{}';
-- Índices GIN para contenção de array eficiente
CREATE INDEX IF NOT EXISTS idx_deaths_occupation_qids ON deaths USING GIN (occupation_qids);
CREATE INDEX IF NOT EXISTS idx_deaths_location_qids   ON deaths USING GIN (location_qids);
```

- `occupation_qids`: cadeia completa de ancestrais P106+P279, incluindo o valor direto. Exemplo: `['Q639669', 'Q177220', 'Q488205']` (baixista → músico → artista).
- `location_qids`: cadeia de P20 + cadeia P131, incluindo o valor direto. Exemplo: `['Q18419', 'Q60', 'Q1384', 'Q30']` (Brooklyn → New York City → New York → USA).
- Ambos NUNCA podem ser `null`; arrays vazios quando dado ausente.

### Tabela `watches` (acréscimos necessários)

```sql
ALTER TABLE watches ADD COLUMN filter_occupation_qid TEXT;
ALTER TABLE watches ADD COLUMN filter_location_qid   TEXT;
-- Restrição: pelo menos um dos dois filtros deve estar preenchido,
-- ou ambos nulos (= assinatura por pessoa específica, sem filtro).
-- Assinatura "filtro sem wiki_title específico" ainda usa wiki_title = '' ou NULL.
```

**Invariante**: `filter_occupation_qid IS NOT NULL OR filter_location_qid IS NOT NULL` para assinaturas por filtro. Assinatura por pessoa específica (wiki_title preenchido, ambos filtros nulos) continua funcionando como hoje.

### Tabela `watch_milestones` (existente — não alterar)

Já existe. Contrato inalterado.

---

## 2. Formato dos IDs

```
Regex obrigatório: ^Q[0-9]+$
```

- Todo QID de Wikidata começa com `Q` maiúsculo seguido de um ou mais dígitos.
- Entradas que não passam neste regex são rejeitadas com HTTP 400 antes de tocar no banco.
- Exemplos válidos: `Q1`, `Q639669`, `Q30`
- Exemplos inválidos: `q1`, `Q`, `Q1;DROP`, `Q1 `, `'OR 1=1`

---

## 3. Funções de enriquecimento

### `enrich_death(wiki_title: str) -> None`

Chamada pelo watcher no GitHub Actions após detectar uma morte. Não roda na Render (restrição de IP).

```python
def enrich_death(wiki_title: str) -> None:
    """
    Busca Wikidata para wiki_title, extrai:
    - P106 (ocupação) com ancestrais P279 (instância de/subclasse de)
    - P20 (local da morte) com ancestrais P131 (localizado em)
    Grava occupation_qids e location_qids em deaths.
    Array vazio se dado ausente — nunca null.
    Limite de profundidade: 10 níveis para P279, 10 para P131.
    Detecta e interrompe ciclos (QID já visto na cadeia atual).
    """
```

**Invariantes testáveis:**
- `occupation_qids` contém o QID direto de P106, se presente
- `location_qids` contém o QID direto de P20, se presente
- Profundidade máxima 10 em cada hierarquia
- Sem ciclos (mesmo QID não aparece duas vezes na mesma cadeia)
- Função idempotente (chamar duas vezes não muda o resultado)
- Arrays vazios (não null) quando dado ausente

### `traverse_hierarchy(qid: str, prop: str, max_depth: int = 10) -> list[str]`

```python
def traverse_hierarchy(qid: str, prop: str, max_depth: int = 10) -> list[str]:
    """
    Retorna [qid] + todos os ancestrais pelo prop P279 ou P131.
    Pára em max_depth ou quando QID já visto (ciclo).
    Retorna lista começando pelo qid direto.
    """
```

---

## 4. Função de match

### `match_watch(watch: dict, death: dict) -> bool`

```python
def match_watch(watch: dict, death: dict) -> bool:
    """
    Retorna True se a assinatura 'watch' deve receber notificação pela morte 'death'.
    
    Regras:
    1. Se watch não tem filtro de profissão nem de lugar: match por wiki_title (comportamento atual).
    2. Se watch tem filtro de profissão: death.occupation_qids deve conter watch.filter_occupation_qid.
    3. Se watch tem filtro de lugar: death.location_qids deve conter watch.filter_location_qid.
    4. Se watch tem ambos os filtros: ambas as condições devem ser satisfeitas (AND).
    5. Array vazio em death = "dado ausente" = não casa.
    
    Nunca lança exceção. Retorna False para qualquer entrada inesperada.
    """
```

**Exemplos de match:**

| Assinatura | Morte | Resultado | Motivo |
|---|---|---|---|
| profissão=Q639669 (baixista) | occupation_qids=['Q639669','Q177220'] | True | contenção direta |
| profissão=Q177220 (músico) | occupation_qids=['Q639669','Q177220'] | True | conteúdo no array |
| profissão=Q177220 (músico) | occupation_qids=['Q36180'] (escritor) | False | não contém |
| lugar=Q18419 (Brooklyn) | location_qids=['Q18419','Q60','Q1384'] | True | contenção direta |
| lugar=Q30 (EUA) | location_qids=['Q18419','Q60','Q1384','Q30'] | True | ancestral |
| lugar=Q30 (EUA) | location_qids=[] | False | dado ausente |
| profissão=Q177220, lugar=Q30 | occupation e location ambos contêm | True | AND |
| profissão=Q177220, lugar=Q30 | occupation ok, location vazio | False | AND, um falhou |

---

## 5. Endpoints de busca de filtros

### `GET /api/filters/occupations?q=<query>`

```json
{
  "results": [
    {"qid": "Q177220", "label": "musician", "description": "person who creates or performs music"},
    {"qid": "Q639669", "label": "bassist", "description": "musician who plays bass guitar"}
  ]
}
```

- Resposta máxima: 20 resultados
- Busca em labels e aliases da Wikidata (via API Wikidata, client-side ou cache)
- QID sempre no formato `^Q[0-9]+$`

### `GET /api/filters/locations?q=<query>`

Mesmo formato que occupations.

### Códigos de erro

| Código | Quando |
|---|---|
| 400 | QID inválido (não passa regex), query ausente |
| 422 | Payload de assinatura com filtro mas sem pelo menos um QID válido |
| 404 | Entidade não encontrada na Wikidata |
| 429 | Rate limit excedido |

---

## 6. Assinatura com filtro (endpoint POST /watch)

Acréscimo ao payload existente:

```json
{
  "wiki_title": "",
  "email": "user@example.com",
  "filter_occupation_qid": "Q177220",
  "filter_location_qid": null
}
```

- `wiki_title` pode ser vazio quando filtros estão presentes
- Pelo menos um de `filter_occupation_qid` ou `filter_location_qid` deve ser não-nulo para assinatura por filtro
- Ambos nulos + wiki_title preenchido = assinatura por pessoa (comportamento atual)
- Ambos nulos + wiki_title vazio = HTTP 400

---

## 7. Janela de enriquecimento

- `ENRICHMENT_GRACE_HOURS` (default: 24h): tempo que assinaturas por filtro esperam pelo enriquecimento Wikidata antes de notificar com dados parciais
- Assinatura por pessoa específica: notifica na hora, sem esperar enriquecimento
- Após a janela: notifica com o que tiver em `occupation_qids` e `location_qids` (pode ser vazio)

---

## 8. Invariantes de qualidade dos arrays

- `occupation_qids` e `location_qids` nunca são `null` no banco; sempre `[]` quando vazio
- O valor direto (P106, P20) sempre está no array (se presente na Wikidata)
- Arrays não têm duplicatas
- Profundidade máxima 10 por hierarquia
- Ciclos detectados e interrompidos

---

## 9. Cobertura dos testes de filtros (xfail)

Todos os testes de filtros são marcados com:
```python
@pytest.mark.xfail(strict=True, reason="filtros pendentes: ver contrato-filtros.md")
```

Quando a implementação chegar, o `strict=True` força a remoção do marcador (teste que passa com `xfail(strict)` é reportado como XPASS e falha o CI, obrigando atualizar o marcador).
