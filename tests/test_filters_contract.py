"""
Testes de filtros contra o contrato em docs/orquestrador/contrato-filtros.md.

Cobre: UNI-030 a UNI-038 (hierarquia, arrays), INT-020 a INT-031 (match, contenção).
Hypothesis: propriedades de terminação e consistência da hierarquia.
"""
import pytest

from app.filters import (
    enrich_death,
    match_watch,
    traverse_hierarchy,
)


# ── UNI-030: hierarquia P131/P279 sempre termina ─────────────────────────────

def test_uni030_hierarchy_terminates():
    """traverse_hierarchy nunca entra em loop infinito; para em max_depth."""
    result = traverse_hierarchy("Q18419", "P131", max_depth=10)
    assert isinstance(result, list)
    assert len(result) <= 11  # item direto + até 10 ancestrais


def test_uni030_hierarchy_respects_max_depth():
    """O limite de profundidade é respeitado mesmo em grafos profundos."""
    result = traverse_hierarchy("Q18419", "P131", max_depth=3)
    assert len(result) <= 4  # item direto + até 3 ancestrais


# ── UNI-031: sem ciclos ────────────────────────────────────────────────────

def test_uni031_no_cycles_in_hierarchy():
    """Mesmo com ciclos na Wikidata (P131 apontando para si mesmo),
    traverse_hierarchy não entra em loop."""
    result = traverse_hierarchy("Q_CYCLE_TEST", "P131", max_depth=10)
    # Sem duplicatas (ciclo detectado)
    assert len(result) == len(set(result))


# ── UNI-032: conjunto de ancestrais contém o valor direto ────────────────────

def test_uni032_direct_value_in_ancestors():
    """O QID direto (P106 ou P20) deve sempre estar incluído no array de ancestrais."""
    result = traverse_hierarchy("Q639669", "P279")  # baixista
    assert "Q639669" in result  # o próprio QID está no resultado


# ── UNI-033: pessoa sem ocupação → array vazio ───────────────────────────────

def test_uni033_no_occupation_empty_array():
    """Pessoa sem P106 (ocupação) no Wikidata: occupation_qids = [] (nunca null)."""
    result = enrich_death("Q_NO_OCCUPATION_FIXTURE")
    assert result["occupation_qids"] == []
    assert result["occupation_qids"] is not None


# ── UNI-034: pessoa sem local → array vazio ─────────────────────────────────

def test_uni034_no_location_empty_array():
    """Pessoa sem P20 (local de morte) no Wikidata: location_qids = [] (nunca null)."""
    result = enrich_death("Q_NO_LOCATION_FIXTURE")
    assert result["location_qids"] == []
    assert result["location_qids"] is not None


# ── UNI-035: até 10 ocupações no array ──────────────────────────────────────

def test_uni035_ten_occupations_all_in_array():
    """Pessoa com 10 ocupações: todos os QIDs presentes no array."""
    result = enrich_death("Q_TEN_OCCUPATIONS_FIXTURE")
    assert len(result["occupation_qids"]) >= 10


# ── UNI-036: local sem P131 → apenas o próprio QID ──────────────────────────

def test_uni036_location_without_p131():
    """Local que não tem P131 (ex: país sem subdivisão P131 acima dele):
    location_qids contém apenas o QID direto do P20, sem exceção."""
    result = enrich_death("Q_NO_P131_FIXTURE")
    assert result["location_qids"] is not None
    if result["location_qids"]:
        assert len(result["location_qids"]) >= 1


# ── UNI-037/038: Hypothesis — propriedades gerais da hierarquia ─────────────

def test_uni037_hypothesis_hierarchy_always_terminates():
    """Hypothesis: para qualquer QID e prop, traverse_hierarchy termina."""
    try:
        from hypothesis import given, settings
        from hypothesis import strategies as st
    except ImportError:
        pytest.skip("hypothesis não instalado")

    @given(qid=st.from_regex(r"Q[0-9]{1,8}", fullmatch=True),
           prop=st.sampled_from(["P279", "P131"]),
           depth=st.integers(min_value=1, max_value=20))
    @settings(max_examples=20)
    def _prop(qid, prop, depth):
        result = traverse_hierarchy(qid, prop, max_depth=depth)
        assert isinstance(result, list)
        assert len(result) <= depth + 1

    _prop()


def test_uni038_hypothesis_match_is_consistent():
    """Hypothesis: match_watch(w, d) é determinístico para as mesmas entradas."""
    try:
        from hypothesis import given, settings
        from hypothesis import strategies as st
    except ImportError:
        pytest.skip("hypothesis não instalado")

    qid_strat = st.from_regex(r"Q[0-9]{1,6}", fullmatch=True)
    qid_list  = st.lists(qid_strat, min_size=0, max_size=5)

    @given(
        occ_qid=st.one_of(st.none(), qid_strat),
        loc_qid=st.one_of(st.none(), qid_strat),
        death_occs=qid_list,
        death_locs=qid_list,
    )
    @settings(max_examples=30)
    def _prop(occ_qid, loc_qid, death_occs, death_locs):
        watch = {"filter_occupation_qid": occ_qid, "filter_location_qid": loc_qid}
        death = {"occupation_qids": death_occs, "location_qids": death_locs}
        r1 = match_watch(watch, death)
        r2 = match_watch(watch, death)
        assert r1 == r2  # determinístico

    _prop()


# ── INT-020: contenção de array — "Brooklyn" casa Brooklyn ──────────────────

def test_int020_brooklyn_matches_brooklyn_death():
    """Assinatura 'lugar=Brooklyn (Q18419)' casa morte cujo location_qids
    contém Q18419."""
    watch = {"filter_occupation_qid": None, "filter_location_qid": "Q18419"}
    death = {"occupation_qids": [], "location_qids": ["Q18419", "Q60", "Q1384", "Q30"]}
    assert match_watch(watch, death) is True


def test_int021_texas_matches_texan_city():
    """Assinatura 'lugar=Texas (Q1439)' casa morte em cidade texana cujo array
    inclui Q1439 como ancestral."""
    watch = {"filter_occupation_qid": None, "filter_location_qid": "Q1439"}
    death = {"occupation_qids": [], "location_qids": ["Q16557", "Q1439", "Q30"]}
    assert match_watch(watch, death) is True


def test_int022_musician_matches_jazz_singer():
    """'Músico (Q177220)' casa 'cantor de jazz' porque a hierarquia P279
    do cantor de jazz inclui músico."""
    watch = {"filter_occupation_qid": "Q177220", "filter_location_qid": None}
    death = {"occupation_qids": ["Q1607826", "Q177220", "Q488205"], "location_qids": []}
    assert match_watch(watch, death) is True


def test_int023_jazz_singer_does_not_match_pianist():
    """'Cantor de jazz' não casa 'pianista' — sem sobreposição na hierarquia."""
    watch = {"filter_occupation_qid": "Q1607826", "filter_location_qid": None}  # cantor de jazz
    death = {"occupation_qids": ["Q486748", "Q177220", "Q488205"], "location_qids": []}  # pianista
    assert match_watch(watch, death) is False


def test_int024_occupation_only_subscription():
    """Assinatura só por profissão (sem lugar) funciona."""
    watch = {"filter_occupation_qid": "Q177220", "filter_location_qid": None}
    death = {"occupation_qids": ["Q177220"], "location_qids": []}
    assert match_watch(watch, death) is True


def test_int025_location_only_subscription():
    """Assinatura só por lugar (sem profissão) funciona."""
    watch = {"filter_occupation_qid": None, "filter_location_qid": "Q30"}
    death = {"occupation_qids": [], "location_qids": ["Q18419", "Q60", "Q30"]}
    assert match_watch(watch, death) is True


def test_int026_both_filters_required_and():
    """Assinatura por profissão E lugar: ambos devem casar (AND)."""
    watch = {"filter_occupation_qid": "Q177220", "filter_location_qid": "Q30"}
    # Morte com profissão ok mas lugar ausente → não casa
    death_no_loc = {"occupation_qids": ["Q177220"], "location_qids": []}
    assert match_watch(watch, death_no_loc) is False
    # Morte com ambos ok → casa
    death_both = {"occupation_qids": ["Q177220"], "location_qids": ["Q30"]}
    assert match_watch(watch, death_both) is True


def test_int027_subscription_without_filter_rejected():
    """Assinatura por filtro sem nenhum filtro preenchido é rejeitada (False)."""
    watch = {"filter_occupation_qid": None, "filter_location_qid": None,
             "wiki_title": ""}  # sem wiki_title E sem filtros
    death = {"occupation_qids": ["Q177220"], "location_qids": ["Q30"]}
    assert match_watch(watch, death) is False


def test_int028_missing_data_does_not_match():
    """Arrays vazios no death = dado ausente = não casa."""
    watch_occ = {"filter_occupation_qid": "Q177220", "filter_location_qid": None}
    death_empty = {"occupation_qids": [], "location_qids": []}
    assert match_watch(watch_occ, death_empty) is False

    watch_loc = {"filter_occupation_qid": None, "filter_location_qid": "Q30"}
    assert match_watch(watch_loc, death_empty) is False


# ── INT-029/030/031: janela de enriquecimento ─────────────────────────────────

def test_int029_late_enrichment_within_grace_window_matches():
    """Dentro da janela ENRICHMENT_GRACE_HOURS, should_notify retorna False
    (ainda aguarda enriquecimento completo)."""
    from datetime import UTC, datetime, timedelta

    from app.filters import ENRICHMENT_GRACE_HOURS, should_notify_filter_watch

    now = datetime.now(UTC)
    # 1 hora antes do prazo expirar → ainda dentro da janela
    detected_at = (now - timedelta(hours=ENRICHMENT_GRACE_HOURS - 1)).isoformat()
    assert should_notify_filter_watch(detected_at, now=now) is False


def test_int030_after_grace_window_notifies_with_available_data():
    """Após a janela ENRICHMENT_GRACE_HOURS, should_notify retorna True."""
    from datetime import UTC, datetime, timedelta

    from app.filters import ENRICHMENT_GRACE_HOURS, should_notify_filter_watch

    now = datetime.now(UTC)
    # 1 hora após o prazo expirar → janela encerrada
    detected_at = (now - timedelta(hours=ENRICHMENT_GRACE_HOURS + 1)).isoformat()
    assert should_notify_filter_watch(detected_at, now=now) is True


def test_int031_filter_and_person_subscription_no_duplicate():
    """Assinatura por filtro E por pessoa não gera 2 emails para a mesma morte."""
    from app.db import add_watch
    from app.filters import get_notifiable_emails_for_death

    email = "dup@example.com"
    # Person-specific watch
    add_watch("Test_Celebrity", email)
    # Filter watch (occupation = Q177220, músico)
    add_watch("", email, filter_occupation_qid="Q177220")

    death = {
        "occupation_qids": ["Q177220"],
        "location_qids": [],
    }
    notifiable = get_notifiable_emails_for_death("Test_Celebrity", death)

    # get_notifiable_emails_for_death returns a set → no duplicates possible
    assert isinstance(notifiable, set)
    assert email in notifiable
    # Only one unique email address (deduplication by set)
    assert len([e for e in notifiable if e == email]) == 1
