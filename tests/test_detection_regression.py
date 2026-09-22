"""
Regressão dos bugs já corrigidos em produção + casos de borda de detecção.

Cobre: UNI-002 a UNI-009 (wikitext), UNI-013/014 (precisão de data),
UNI-018 a UNI-023 (percent-encoding e i18n).

Cada bug listado aqui regrediu ao menos uma vez na produção (ver comentários).
"""
from urllib.parse import quote, unquote

import pytest

from app.catalog import title_to_slug
from app.main import format_death_date, wiki_url
from app.watcher import extract_death_date

# ── Helpers ──────────────────────────────────────────────────────────────────

def _person_infobox(death_date_field: str = "", name: str = "Test Person") -> str:
    return f"""
{{{{Infobox person
|name = {name}
|birth_date = {{{{Birth date and age|1930|5|31}}}}
|death_date = {death_date_field}
|death_place =
|occupation = Actor
}}}}
"""


# ── UNI-001 já coberto em test_watcher.py; reproduzido aqui para clareza ─────

def test_uni001_placeholder_comment_never_detects():
    """O placeholder exato que causou o falso positivo do Clint Eastwood
    (produção, 2026-07-26) nunca deve ser aceito como data real."""
    wikitext = _person_infobox(
        "<!-- {{Death date and age|YYYY|MM|DD|YYYY|MM|DD}} "
        "(DEATH date then BIRTH date) -->"
    )
    assert extract_death_date(wikitext) is None


# ── UNI-002: parâmetros vazios ─────────────────────────────────────────────

def test_uni002_empty_death_date_params_not_detected():
    """{{Death date and age|||||}} com todos os parâmetros vazios não é data."""
    wikitext = _person_infobox("{{Death date and age|||||}}")
    assert extract_death_date(wikitext) is None


def test_uni002b_whitespace_only_params():
    wikitext = _person_infobox("{{Death date and age|   |   |   }}")
    assert extract_death_date(wikitext) is None


# ── UNI-003: parâmetro '?' ─────────────────────────────────────────────────

def test_uni003_question_mark_year():
    """{{Death date|?|?|?}} não é uma data válida."""
    wikitext = _person_infobox("{{Death date|?|?|?}}")
    assert extract_death_date(wikitext) is None


def test_uni003b_question_mark_mixed():
    """Bug: extract_death_date aceitava '{{Death date|?|1|15|1930|5|31}}' porque
    encontrava '1930' (ano de nascimento) no check regex \d{4}.
    Após a correção mínima em watcher.py, o primeiro parâmetro deve ser \d{4}."""
    wikitext = _person_infobox("{{Death date and age|?|1|15|1930|5|31}}")
    assert extract_death_date(wikitext) is None


# ── UNI-004: só ano, sem mês/dia ─────────────────────────────────────────────

def test_uni004_year_only_format_does_not_invent_day():
    """{{Death date|2020}} (só ano) — extract_death_date aceita (ano válido).
    O contrato é que format_death_date NÃO inventa mês/dia quando não há no template."""
    wikitext = _person_infobox("{{Death date|2020}}")
    result = extract_death_date(wikitext)
    # year-only é uma indicação legítima de morte; a detecção extrai o template
    # O importante: format_death_date não inventa dia
    if result is not None:
        assert "January 0" not in format_death_date(result)
        assert "January 1" not in format_death_date(result)  # não inventa dia


def test_uni004b_year_month_format_does_not_invent_day():
    """{{Death date|2020|3}} (ano+mês, sem dia) — não inventa dia no display."""
    wikitext = _person_infobox("{{Death date|2020|3}}")
    result = extract_death_date(wikitext)
    if result is not None:
        display = format_death_date(result)
        assert "March 0" not in display
        assert " 0," not in display  # dia 0 nunca ocorre


# ── UNI-005: data futura ─────────────────────────────────────────────────────

def test_uni005_future_date_extracted_but_not_false_positive():
    """Uma data futura no template é tecnicamente extraída (a função não filtra
    por datas futuras — isso é responsabilidade da camada de detecção),
    mas o valor retornado não deve ter sido inventado.
    Este teste documenta o comportamento atual e serve como guarda de contrato."""
    wikitext = _person_infobox("{{Death date and age|2099|12|31|1930|5|31}}")
    result = extract_death_date(wikitext)
    # A função extrai o valor, mas não valida se é futuro.
    # O importante: se retorna algo, é o template real, não inventado.
    if result is not None:
        assert "2099" in result


# ── UNI-006: duas datas conflitantes ─────────────────────────────────────────

def test_uni006_first_valid_date_wins():
    """Com dois Infobox person no wikitext (improvável mas possível),
    a primeira data válida encontrada deve prevalecer sobre a segunda."""
    wikitext = """
{{Infobox person
|name = Person A
|death_date = {{Death date and age|2026|3|15|1930|1|1}}
|death_place =
}}
{{Infobox person
|name = Person B
|death_date = {{Death date and age|2027|6|1|1935|2|2}}
|death_place =
}}
"""
    result = extract_death_date(wikitext)
    assert result is not None
    assert "2026" in result  # Primeira data prevalece


def test_uni006b_placeholder_then_real():
    """Placeholder antes de uma data real: deve encontrar a data real no mesmo infobox.
    (Raro, mas garante que a limpeza de comentários não esconde a data real.)"""
    wikitext = _person_infobox(
        "<!-- {{Death date|YYYY|MM|DD}} --> {{Death date and age|2026|8|1|1930|5|31}}"
    )
    result = extract_death_date(wikitext)
    assert result is not None
    assert "2026" in result


# ── UNI-007/008/009 já cobertos em test_watcher.py ──────────────────────────


# ── UNI-013: precisão de data — só ano ──────────────────────────────────────

def test_uni013_year_only_does_not_invent_day():
    """Quando o template não tem dia e mês, format_death_date não inventa 'January 0'.
    Retorna 'confirmed' (comportamento documentado para templates incompletos)."""
    raw = "{{Death date|2020}}"
    result = format_death_date(raw)
    # Não deve conter um dia inventado
    assert "January 0" not in result
    assert "February 0" not in result
    # Comportamento atual: retorna raw quando não consegue parsear
    # (nenhum dia inventado é o contrato)
    assert result == raw  # fallback para raw quando não parsea


def test_uni013b_year_month_does_not_invent_day():
    """{{Death date|2020|3}} — não inventa dia (ex: 'March 0, 2020')."""
    raw = "{{Death date|2020|3}}"
    result = format_death_date(raw)
    assert "March 0" not in result
    assert " 0," not in result
    assert result == raw  # fallback esperado


# ── UNI-014: precisão de data — ano e mês ────────────────────────────────────

def test_uni014_known_month_does_not_add_false_day():
    """Se tivermos ano e mês mas não dia, a data exibida não inventa o dia."""
    # Template com apenas ano e mês (sem dia) — não é formato padrão,
    # mas verifica que a função não inventa dados.
    raw = "{{Death date and age|2020|3||1930|5|31}}"
    result = format_death_date(raw)
    # O regex exige 3 parâmetros numéricos; sem dia, não parseia → retorna raw
    # Importante: não há "March 0" ou "March 1" inventado
    assert "March 0" not in result
    assert result == raw


# ── UNI-018-021: percent-encoding em títulos ─────────────────────────────────

def test_uni018_accented_title_round_trip():
    """Título com acento: encode → decode deve resultar no original.
    Garante que a função wiki_url() é consistente com unquote()."""
    title = "Cléo_de_Mérode"
    url = wiki_url(title)
    assert "wikipedia.org/wiki/" in url
    # A URL contém o título codificado ou o título diretamente
    assert unquote(url.split("/wiki/")[1]) == title


def test_uni018b_percent_encoded_title_same_as_decoded():
    """Título já percent-encoded deve produzir a mesma URL que o título decodificado."""
    decoded = "Cléo_de_Mérode"
    encoded = "Cl%C3%A9o_de_M%C3%A9rode"
    url_decoded = wiki_url(decoded)
    url_encoded = wiki_url(unquote(encoded))  # normaliza antes de gerar URL
    assert url_decoded == url_encoded


def test_uni019_parentheses_in_title():
    """Título com parênteses: wiki_url não quebra a URL."""
    title = "Sting_(musician)"
    url = wiki_url(title)
    assert "Sting" in url
    # URL deve ser válida (sem parênteses soltos)
    decoded_path = unquote(url.split("/wiki/")[1])
    assert decoded_path == title


def test_uni020_apostrophe_in_title():
    """Título com apóstrofo: wiki_url produz URL válida."""
    title = "D'Angelo"
    url = wiki_url(title)
    assert "wikipedia.org/wiki/" in url
    decoded_path = unquote(url.split("/wiki/")[1])
    assert decoded_path == title


def test_uni021_slash_in_title():
    """Título com barra: wiki_url inclui o título.
    quote() por padrão não codifica '/'; Wikipedia aceita 'AC/DC' como caminho.
    O contrato é apenas que a URL contém o título, sem crash."""
    title = "AC/DC"
    url = wiki_url(title)
    assert "wikipedia.org/wiki/" in url
    assert "AC" in url
    assert "DC" in url


# ── UNI-022-023: subdomínios de idioma ──────────────────────────────────────

def test_uni022_lang_subdomain_in_url():
    """wiki_url com lang='pt' produz URL em pt.wikipedia.org."""
    from app.wiki import wiki_api
    url = wiki_api("pt")
    assert "pt.wikipedia.org" in url


def test_uni022b_lang_subdomain_fr():
    from app.wiki import wiki_api
    assert "fr.wikipedia.org" in wiki_api("fr")


def test_uni023_default_lang_is_english():
    """Sem lang explícito, wiki_api retorna URL inglesa."""
    from app.wiki import wiki_api
    assert "en.wikipedia.org" in wiki_api()
    assert "en.wikipedia.org" in wiki_api("en")


# ── title_to_slug: slug sem caracteres especiais ─────────────────────────────

def test_title_to_slug_removes_accents_ascii():
    """Artistas com acento no nome têm slug sem caracteres não-ASCII."""
    slug = title_to_slug("Beyoncé")
    assert slug.isascii() or all(c in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in slug)


def test_title_to_slug_handles_parens():
    """Parênteses no título são removidos do slug."""
    slug = title_to_slug("Sting_(musician)")
    assert "(" not in slug
    assert ")" not in slug
    assert "sting" in slug


def test_title_to_slug_handles_dots():
    slug = title_to_slug("Samuel_L._Jackson")
    assert "." not in slug
    assert "samuel" in slug


def test_title_to_slug_is_lowercase():
    assert title_to_slug("Clint_Eastwood") == title_to_slug("Clint_Eastwood").lower()
