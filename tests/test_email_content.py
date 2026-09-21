"""
Testes de conteúdo de email — EML-001 a EML-011.

EML-001/002: Subject e HTML sem wikitext bruto (intercepta httpx.post via mock).
EML-003: Versão texto ausente → xfail.
EML-004: Link de cancelamento ausente → xfail.
EML-005/006: List-Unsubscribe headers ausentes → xfail.
EML-007 a EML-011: Verificações DNS e entrega @live — skip sem flag --run-live.

Nota: RESEND_API_KEY ausente faz send_* retornar False silenciosamente.
Os testes EML-001/002 mockam httpx.post para capturar o payload mesmo sem chave.
"""
import re
from unittest.mock import MagicMock, patch

import pytest


# Fixture que intercepta httpx.post e retorna status 200
@pytest.fixture()
def capture_resend():
    """Intercepta a chamada real a api.resend.com e devolve o payload enviado."""
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None, **kw):
        calls.append({"url": url, "headers": headers or {}, "json": json or {}})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"id":"fake-id"}'
        return mock_resp

    with patch("app.email.RESEND_API_KEY", "fake-key-for-test"):
        with patch("httpx.post", side_effect=fake_post):
            yield calls


# ── EML-001: assunto sem wikitext bruto ──────────────────────────────────────

def test_eml001_subject_has_no_raw_wikitext(capture_resend):
    """O assunto do email nunca deve conter '{{' ou '}}' de templates wikitext.
    O watcher pode armazenar o template bruto em deaths.death_date — o email
    deve mostrar a data formatada, nunca o template."""
    from app.email import send_death_notification

    send_death_notification(
        to_email="fan@example.com",
        person_name="Test Person",
        wiki_title="Test_Person",
        death_date="{{Death date and age|2026|3|15|1940|1|1}}",
        wiki_url="https://en.wikipedia.org/wiki/Test_Person",
    )

    assert len(capture_resend) == 1
    subject = capture_resend[0]["json"]["subject"]
    assert "{{" not in subject, f"Template bruto no assunto: {subject!r}"
    assert "}}" not in subject, f"Template bruto no assunto: {subject!r}"


def test_eml001_subject_contains_person_name(capture_resend):
    """O assunto do email deve conter o nome da pessoa."""
    from app.email import send_death_notification

    send_death_notification(
        to_email="fan@example.com",
        person_name="Jane Goodall",
        wiki_title="Jane_Goodall",
        death_date="October 1, 2025",
        wiki_url="https://en.wikipedia.org/wiki/Jane_Goodall",
    )

    subject = capture_resend[0]["json"]["subject"]
    assert "Jane Goodall" in subject


# ── EML-002: corpo HTML sem wikitext bruto ───────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="Bug conhecido: email.py insere death_date diretamente no f-string "
           "sem formatar. O campo death_date salvo no banco pode conter wikitext "
           "bruto (ex: '{{Death date and age|...}}') que aparece verbatim no email. "
           "Fix: passar format_death_date(death_date) antes de montar o HTML.",
)
def test_eml002_html_body_has_no_raw_wikitext_template(capture_resend):
    """O corpo HTML nunca deve expor o template wikitext bruto para o leitor.
    A data deve vir já formatada ('March 15, 2026'), não como '{{Death date...}}'."""
    from app.email import send_death_notification

    send_death_notification(
        to_email="fan@example.com",
        person_name="Test Person",
        wiki_title="Test_Person",
        death_date="{{Death date and age|2026|3|15|1940|1|1}}",
        wiki_url="https://en.wikipedia.org/wiki/Test_Person",
    )

    html_body = capture_resend[0]["json"]["html"]
    # O template wikitext não deve aparecer verbatim no HTML
    assert "{{Death date" not in html_body, "Template wikitext bruto no corpo HTML"
    assert "{{death date" not in html_body.lower()


def test_eml002_html_body_has_person_name(capture_resend):
    """O corpo HTML deve conter o nome da pessoa."""
    from app.email import send_death_notification

    send_death_notification(
        to_email="recipient@example.com",
        person_name="Clint Eastwood",
        wiki_title="Clint_Eastwood",
        death_date="confirmed",
        wiki_url="https://en.wikipedia.org/wiki/Clint_Eastwood",
    )

    html_body = capture_resend[0]["json"]["html"]
    assert "Clint Eastwood" in html_body


def test_eml002_html_body_contains_wikipedia_link(capture_resend):
    """O corpo HTML deve conter um link para o artigo da Wikipedia."""
    from app.email import send_death_notification

    wiki_url = "https://en.wikipedia.org/wiki/Test_Person"
    send_death_notification(
        to_email="fan@example.com",
        person_name="Test Person",
        wiki_title="Test_Person",
        death_date="confirmed",
        wiki_url=wiki_url,
    )

    html_body = capture_resend[0]["json"]["html"]
    assert wiki_url in html_body


@pytest.mark.xfail(
    strict=True,
    reason="Bug conhecido: email.py insere death_date (placeholder HTML comentado) "
           "diretamente no f-string. O placeholder '<!-- {{Death date...}} -->' "
           "aparece verbatim no corpo do email.",
)
def test_eml002_html_body_no_placeholder_visible(capture_resend):
    """O placeholder exato que causou o bug de Clint Eastwood nunca deve aparecer
    no corpo do email como texto visível."""
    from app.email import send_death_notification

    placeholder = "<!-- {{Death date and age|YYYY|MM|DD|YYYY|MM|DD}} (DEATH date then BIRTH date) -->"
    send_death_notification(
        to_email="fan@example.com",
        person_name="Test Person",
        wiki_title="Test_Person",
        death_date=placeholder,
        wiki_url="https://en.wikipedia.org/wiki/Test_Person",
    )

    html_body = capture_resend[0]["json"]["html"]
    # O placeholder pode aparecer em HTML mas não como conteúdo visível
    # O contrato mais fraco: não deve conter "YYYY|MM|DD" como texto puro
    assert "YYYY|MM|DD" not in html_body


# ── EML-003: versão texto ausente (xfail) ────────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="Versão texto do email não implementada: send_death_notification "
           "envia apenas HTML, sem fallback text/plain",
)
def test_eml003_plain_text_version_present(capture_resend):
    """Emails de notificação devem ter versão texto para clientes sem HTML
    e para melhores métricas de entrega."""
    from app.email import send_death_notification

    send_death_notification(
        to_email="fan@example.com",
        person_name="Test Person",
        wiki_title="Test_Person",
        death_date="March 15, 2026",
        wiki_url="https://en.wikipedia.org/wiki/Test_Person",
    )

    payload = capture_resend[0]["json"]
    assert "text" in payload, "Campo 'text' ausente no payload do Resend (versão texto não enviada)"


# ── EML-004: link de cancelamento ausente (xfail) ────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="Link de cancelamento não implementado: email.py não inclui "
           "URL de unsubscribe; ver EML-004 e contrato",
)
def test_eml004_cancel_link_present_in_html(capture_resend):
    """O corpo HTML deve conter link de cancelamento de assinatura."""
    from app.email import send_death_notification

    send_death_notification(
        to_email="fan@example.com",
        person_name="Test Person",
        wiki_title="Test_Person",
        death_date="March 15, 2026",
        wiki_url="https://en.wikipedia.org/wiki/Test_Person",
    )

    html_body = capture_resend[0]["json"]["html"]
    # Deve haver um link de unsubscribe/cancelamento
    has_cancel = (
        "unsubscribe" in html_body.lower()
        or "cancel" in html_body.lower()
        or "/cancel" in html_body
    )
    assert has_cancel, "Nenhum link de cancelamento encontrado no HTML do email"


# ── EML-005: List-Unsubscribe header ausente (xfail) ─────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="List-Unsubscribe header não implementado: payload do Resend "
           "não inclui headers de unsubscribe; obrigatório para Gmail/Yahoo 2024",
)
def test_eml005_list_unsubscribe_header_present(capture_resend):
    """O email deve incluir List-Unsubscribe conforme exigido pelo Gmail/Yahoo (2024)."""
    from app.email import send_death_notification

    send_death_notification(
        to_email="fan@example.com",
        person_name="Test Person",
        wiki_title="Test_Person",
        death_date="March 15, 2026",
        wiki_url="https://en.wikipedia.org/wiki/Test_Person",
    )

    payload = capture_resend[0]["json"]
    headers = payload.get("headers", {})
    assert "List-Unsubscribe" in headers or "list-unsubscribe" in {k.lower() for k in headers}


# ── EML-006: List-Unsubscribe-Post header ausente (xfail) ────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="List-Unsubscribe-Post header não implementado: necessário para "
           "one-click unsubscribe (RFC 8058, Gmail 2024)",
)
def test_eml006_list_unsubscribe_post_header_present(capture_resend):
    """O email deve incluir List-Unsubscribe-Post para one-click unsubscribe."""
    from app.email import send_death_notification

    send_death_notification(
        to_email="fan@example.com",
        person_name="Test Person",
        wiki_title="Test_Person",
        death_date="March 15, 2026",
        wiki_url="https://en.wikipedia.org/wiki/Test_Person",
    )

    payload = capture_resend[0]["json"]
    headers = payload.get("headers", {})
    header_keys_lower = {k.lower() for k in headers}
    assert "list-unsubscribe-post" in header_keys_lower


# ── EML-007 a EML-011: verificações DNS e entrega @live ──────────────────────

pytestmark_live = pytest.mark.skipif(
    True,  # Sempre skip em CI; rodar com pytest -m live para ativar
    reason="@live: requer DNS real e credenciais de email; rodar fora do CI",
)


@pytestmark_live
def test_eml007_spf_record_present():
    """SPF para noreply@mortivox.com deve estar presente (v=spf1...)."""
    import dns.resolver  # type: ignore[import-untyped]

    answers = dns.resolver.resolve("mortivox.com", "TXT")
    spf_records = [str(r) for r in answers if "v=spf1" in str(r).lower()]
    assert spf_records, "Nenhum registro SPF encontrado para mortivox.com"


@pytestmark_live
def test_eml008_dkim_record_present():
    """DKIM para resend._domainkey.mortivox.com deve estar presente."""
    import dns.resolver  # type: ignore[import-untyped]

    answers = dns.resolver.resolve("resend._domainkey.mortivox.com", "TXT")
    dkim_records = [str(r) for r in answers]
    assert dkim_records, "DKIM ausente para mortivox.com"


@pytestmark_live
def test_eml009_dmarc_record_present():
    """DMARC para _dmarc.mortivox.com deve estar presente."""
    import dns.resolver  # type: ignore[import-untyped]

    answers = dns.resolver.resolve("_dmarc.mortivox.com", "TXT")
    dmarc_records = [str(r) for r in answers if "v=dmarc1" in str(r).lower()]
    assert dmarc_records, "DMARC ausente para mortivox.com"


@pytestmark_live
def test_eml010_bounce_suppresses_future_sends():
    """Bounce de entrega deve suprimir envios futuros a esse endereço.
    Requer integração com webhooks do Resend."""
    pytest.skip("Requer integração com webhook de bounce do Resend; implementação pendente")


@pytestmark_live
def test_eml011_complaint_suppresses_future_sends():
    """Reclamação de spam deve suprimir envios futuros.
    Requer integração com webhooks do Resend."""
    pytest.skip("Requer integração com webhook de complaint do Resend; implementação pendente")
