"""
Testes de integração: idempotência de notificação, milestones, fuso horário.

Cobre: INT-001 (morte detectada 2x → 1 email), INT-007 (milestones),
INT-008 (UTC), INT-003 marcado xfail (cancelamento não implementado).

Usa SQLite isolado via conftest.py (autouse fixture).
Email real NÃO é enviado: RESEND_API_KEY ausente → email.py retorna False silenciosamente.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.db import (
    add_watch,
    get_emails_for,
    is_already_dead,
    record_death,
)
from app.milestones import (
    get_notified_milestones,
    init_milestones_table,
    record_milestone,
)

# ── INT-001: mesma morte → exatamente 1 email ────────────────────────────────

def test_int001_death_recorded_only_once():
    """Duas chamadas a record_death para o mesmo título: apenas a primeira
    insere, a segunda retorna False (ON CONFLICT ... DO NOTHING)."""
    first  = record_death("Test_Person", "Test Person", "{{Death date and age|2026|1|1|1930|1|1}}")
    second = record_death("Test_Person", "Test Person", "{{Death date and age|2026|1|1|1930|1|1}}")
    assert first is True
    assert second is False


def test_int001_is_already_dead_prevents_second_notification():
    """O loop do watcher checa is_already_dead antes de processar.
    Após a primeira detecção, is_already_dead retorna True e o watcher pula."""
    add_watch("Celebrity_A", "fan@example.com")
    assert is_already_dead("Celebrity_A") is False

    record_death("Celebrity_A", "Celebrity A", "{{Death date and age|2026|6|15|1940|1|1}}")
    assert is_already_dead("Celebrity_A") is True


def test_int001_only_one_email_sent_for_same_death():
    """Simula o fluxo completo do watcher: duas detecções do mesmo evento.
    Apenas 1 email deve ser disparado para o assinante."""
    add_watch("Pop_Star", "fan1@example.com")
    add_watch("Pop_Star", "fan2@example.com")

    email_calls = []

    def mock_send(to_email, person_name, wiki_title, death_date, wiki_url, edit_url=None):
        email_calls.append(to_email)
        return True

    with patch("app.email.send_death_notification", side_effect=mock_send):
        # Primeira detecção
        is_new_1 = record_death("Pop_Star", "Pop Star", "{{Death date and age|2026|7|1|1985|1|1}}")
        if is_new_1:
            emails = get_emails_for("Pop_Star")
            from app.email import send_death_notification
            for e in emails:
                send_death_notification(e, "Pop Star", "Pop_Star", "July 1, 2026",
                                         "https://en.wikipedia.org/wiki/Pop_Star")

        # Segunda detecção (watcher simulado rodando de novo)
        is_new_2 = record_death("Pop_Star", "Pop Star", "{{Death date and age|2026|7|1|1985|1|1}}")
        if is_new_2:
            emails = get_emails_for("Pop_Star")
            from app.email import send_death_notification as send2
            for e in emails:
                send2(e, "Pop Star", "Pop_Star", "July 1, 2026",
                      "https://en.wikipedia.org/wiki/Pop_Star")

    # Primeira detecção enviou 2 emails (2 assinantes); segunda não enviou nenhum
    assert len(email_calls) == 2
    assert is_new_1 is True
    assert is_new_2 is False


# ── INT-002: execuções simultâneas (race condition) ───────────────────────────

def test_int002_record_death_unique_constraint():
    """A restrição UNIQUE em deaths.wiki_title garante que em concorrência
    apenas uma das inserções simultâneas tem rowcount=1.
    Este teste verifica o contrato do banco; o teste de concorrência real
    requer Postgres e está marcado PENDENTE_DE_BANCO."""
    r1 = record_death("Concurrent_Test", "Concurrent Test", "{{Death date and age|2026|1|1|1930|1|1}}")
    r2 = record_death("Concurrent_Test", "Concurrent Test", "{{Death date and age|2026|1|1|1930|1|1}}")
    # Apenas uma inserção bem-sucedida
    assert r1 is True
    assert r2 is False


# ── INT-003: assinante cancelado (xfail — cancelamento não implementado) ──────

@pytest.mark.xfail(
    strict=True,
    reason="cancelamento de assinatura não implementado: sem endpoint /cancel "
           "nem remove_watch(); ver EML-004 e contrato",
)
def test_int003_cancelled_subscriber_does_not_receive():
    """Assinante que cancelou antes do envio não deve receber notificação.
    Requer endpoint de cancelamento e função remove_watch()."""
    from app.db import remove_watch  # não existe ainda → ImportError → xfail
    add_watch("Test_Celebrity", "will.unsubscribe@example.com")
    remove_watch("Test_Celebrity", "will.unsubscribe@example.com")
    emails = get_emails_for("Test_Celebrity")
    assert "will.unsubscribe@example.com" not in emails


# ── INT-007: milestones — limiar cruzado uma vez ─────────────────────────────

def test_int007_milestone_recorded_only_once():
    """Um milestone (ex: 10 watchers) deve ser registrado apenas uma vez
    para o mesmo wiki_title. A restrição PRIMARY KEY (wiki_title, milestone)
    garante isso."""
    init_milestones_table()
    record_milestone("Milestone_Test", 10)
    record_milestone("Milestone_Test", 10)  # duplicata ignorada
    notified = get_notified_milestones("Milestone_Test")
    assert notified == {10}


def test_int007_multiple_milestones_tracked_independently():
    """Milestones diferentes para o mesmo título são rastreados de forma independente."""
    init_milestones_table()
    record_milestone("Multi_Milestone", 10)
    record_milestone("Multi_Milestone", 50)
    notified = get_notified_milestones("Multi_Milestone")
    assert 10 in notified
    assert 50 in notified
    assert 100 not in notified


def test_int007_new_milestone_detected_when_threshold_crossed():
    """Lógica de detecção de milestones: count >= milestone e não notificado."""
    from app.milestones import MILESTONES

    # Simula: pessoa com 12 watchers, milestone 10 ainda não notificado
    init_milestones_table()
    count = 12
    already_notified: set[int] = set()  # nenhum milestone ainda
    new_milestones = [m for m in MILESTONES if m <= count and m not in already_notified]
    assert 10 in new_milestones
    assert 50 not in new_milestones  # 50 > 12


def test_int007_crossed_milestone_not_repeated():
    """Uma vez notificado, o milestone não reaparece nos novos."""
    from app.milestones import MILESTONES

    init_milestones_table()
    record_milestone("Repeat_Test", 10)
    already_notified = get_notified_milestones("Repeat_Test")

    count = 15
    new_milestones = [m for m in MILESTONES if m <= count and m not in already_notified]
    assert 10 not in new_milestones  # já notificado


# ── INT-008: fuso horário UTC — virada de dia não desloca data da morte ────────

def test_int008_death_date_from_template_not_from_detection_time():
    """A data de morte exibida vem do template wikitext, não do detected_at.
    Uma virada de dia UTC no momento da detecção não deve alterar a data da morte."""
    from app.main import format_death_date

    # Morte aconteceu em 31 de dezembro de 2025
    death_wikitext = "{{Death date and age|2025|12|31|1940|1|1}}"
    # detected_at poderia ser 00:01 UTC de 1 de janeiro de 2026 (virada de dia)
    # Mas a data exibida vem do template, não de detected_at
    displayed_date = format_death_date(death_wikitext)
    assert displayed_date == "December 31, 2025"
    assert "January" not in displayed_date  # não deslocou para o dia seguinte


def test_int008_detected_at_timezone_does_not_affect_display():
    """detection_label usa só os 10 primeiros chars do detected_at (YYYY-MM-DD),
    sem conversão de timezone. Garante que timestamps UTC não deslocam a data."""
    from app.main import detection_label

    # Detectado às 23:59:59 UTC em 31 de dezembro
    label = detection_label("2025-12-31T23:59:59+00:00",
                            "{{Death date and age|2025|12|31|1940|1|1}}")
    assert "2025-12-31" in label
    assert "2026" not in label  # não avançou para 2026
