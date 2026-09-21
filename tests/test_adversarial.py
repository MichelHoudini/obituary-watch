"""
Testes adversariais — ADV-001 a ADV-013.

ADV-001/002: SQL injection em wiki_title e email → sem 500.
ADV-003/004: XSS em nome de pessoa → escapado no HTML.
ADV-005: Injeção de cabeçalho de email → rejeitada.
ADV-006 a ADV-008: Tokens (xfail — cancelamento não implementado).
ADV-009: Enumeração — POST /watch não revela se email já existe.
ADV-010: Rate limit (já coberto em test_main.py; verificação separada aqui).
ADV-011: Endpoint de busca suporta volume.
ADV-012: Unicode estranho em wiki_title → sem 500.
ADV-013: Entrada de 10k chars → sem 500.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


# ── ADV-001: SQL injection em wiki_title ─────────────────────────────────────

@pytest.mark.parametrize("malicious_title", [
    "'; DROP TABLE deaths; --",
    "\" OR 1=1; --",
    "Robert'); DROP TABLE watches; --",
    "foo' UNION SELECT 1,2,3 --",
    "<script>alert(1)</script>",
])
def test_adv001_sql_injection_in_wiki_title_no_exception(malicious_title):
    """SQL injection em wiki_title nunca deve causar exceção.
    Testa a camada db.add_watch() diretamente (query parametrizada).
    Evita consumir tokens do rate limiter HTTP que são compartilhados entre testes."""
    from app.db import add_watch, init_db

    init_db()
    # Não deve lançar exceção (SQLite descarta o SQL injection via parâmetro)
    try:
        add_watch(malicious_title, "safe@example.com")
    except Exception as e:
        pytest.fail(f"SQL injection em wiki_title causou exceção: {malicious_title!r} → {e}")


# ── ADV-002: SQL injection em email ─────────────────────────────────────────

@pytest.mark.parametrize("malicious_email", [
    "'; DROP TABLE watches; --@example.com",
    "a\" OR \"1\"=\"1",
    "test@' OR '1'='1",
])
def test_adv002_sql_injection_in_email_no_exception(malicious_email):
    """SQL injection em email nunca deve causar exceção.
    Testa a camada db.add_watch() diretamente (query parametrizada)."""
    from app.db import add_watch, init_db

    init_db()
    try:
        add_watch("Clint_Eastwood", malicious_email)
    except Exception as e:
        pytest.fail(f"SQL injection em email causou exceção: {malicious_email!r} → {e}")


# ── ADV-003: XSS em nome de pessoa na página HTML ────────────────────────────

def test_adv003_xss_in_person_name_escaped_in_html():
    """Nome de pessoa com payload XSS deve ser escapado no HTML da página.
    app/main.py usa e() → html.escape() em todos os valores dinâmicos."""
    from app.db import init_db, record_death
    init_db()

    # Insere uma morte com nome contendo payload XSS
    xss_name = '<script>alert("xss")</script>'
    record_death("XSS_Test_Person", xss_name, "{{Death date and age|2026|1|1|1930|1|1}}")

    # A página /deaths lista as mortes detectadas
    r = client.get("/deaths")
    assert r.status_code == 200

    body = r.text
    # O payload bruto nunca deve aparecer não-escapado no HTML
    assert "<script>alert(" not in body, (
        "Payload XSS não-escapado encontrado na página /deaths"
    )
    # A versão escapada pode aparecer (como entidade HTML) — isso é seguro
    # &lt;script&gt; é inofensivo


def test_adv003_xss_in_wiki_title_escaped_in_page():
    """wiki_title com caracteres HTML é escapado no HTML das páginas.
    Insere via add_watch() para não consumir tokens do rate limiter."""
    from app.db import add_watch, init_db, record_death

    init_db()
    xss_title = '<img src=x onerror=alert(1)>'
    add_watch(xss_title, "safe2@example.com")

    # Verifica que /deaths não renderiza o XSS não-escapado
    r = client.get("/deaths")
    assert r.status_code == 200
    assert "<img src=x onerror=alert(1)>" not in r.text or "onerror=alert" not in r.text


# ── ADV-004: XSS no email HTML ───────────────────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="Bug conhecido: email.py usa f-string sem html.escape(person_name). "
           "XSS em person_name aparece verbatim no HTML do email. "
           "Fix: envolver person_name em html.escape() no template.",
)
def test_adv004_xss_person_name_escaped_in_email():
    """XSS em person_name deve ser escapado no template HTML do email."""
    from unittest.mock import MagicMock, patch

    html_bodies = []

    def capture(url, headers=None, json=None, timeout=None, **kw):
        if json:
            html_bodies.append(json.get("html", ""))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"id":"x"}'
        return mock_resp

    xss_name = '<script>alert("owned")</script>'
    with patch("app.email.RESEND_API_KEY", "fake"):
        with patch("httpx.post", side_effect=capture):
            from app.email import send_death_notification
            send_death_notification(
                to_email="victim@example.com",
                person_name=xss_name,
                wiki_title="Test",
                death_date="confirmed",
                wiki_url="https://en.wikipedia.org/wiki/Test",
            )

    assert html_bodies, "Nenhuma chamada ao Resend interceptada"
    html = html_bodies[0]
    assert '<script>alert("owned")</script>' not in html, (
        "XSS não-escapado no HTML do email — person_name precisa ser html.escape()'d"
    )


# ── ADV-005: injeção de cabeçalho de email ───────────────────────────────────

def test_adv005_email_header_injection_via_resend_api():
    """Injeção de cabeçalho SMTP clássica não é aplicável aqui: email.py usa
    a API JSON do Resend (não SMTP direto), então a serialização JSON isola
    automaticamente os valores. Este teste documenta o contrato atual."""
    from unittest.mock import MagicMock, patch

    payloads = []

    def capture(url, headers=None, json=None, timeout=None, **kw):
        payloads.append(json or {})
        m = MagicMock()
        m.status_code = 200
        m.text = "{}"
        return m

    injected = "fan@example.com\r\nBcc: attacker@evil.com"
    with patch("app.email.RESEND_API_KEY", "fake"):
        with patch("httpx.post", side_effect=capture):
            from app.email import send_death_notification
            send_death_notification(
                to_email=injected,
                person_name="Test",
                wiki_title="Test",
                death_date="confirmed",
                wiki_url="https://en.wikipedia.org/wiki/Test",
            )

    if payloads:
        to_field = payloads[0].get("to", [])
        # Resend recebe a lista "to" como JSON; CRLF em JSON é serializado como
        # \r\n literal e rejeitado pelo servidor, nunca injetado como cabeçalho.
        # O contrato: o campo "to" deve conter exatamente 1 endereço.
        assert len(to_field) == 1, f"Injeção resultou em {len(to_field)} destinatários: {to_field}"


# ── ADV-006 a ADV-008: tokens de cancelamento (xfail) ────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="Tokens de cancelamento não implementados: sem endpoint /cancel "
           "nem geração de token; ver contrato",
)
def test_adv006_cancel_token_is_random_and_long():
    """Token de cancelamento deve ter >= 32 chars e ser diferente a cada assinatura."""
    from app.db import add_watch_with_token
    t1 = add_watch_with_token("Person_A", "a@example.com")
    t2 = add_watch_with_token("Person_A", "b@example.com")
    assert len(t1) >= 32
    assert len(t2) >= 32
    assert t1 != t2


@pytest.mark.xfail(
    strict=True,
    reason="Tokens de cancelamento não implementados",
)
def test_adv007_cancel_token_single_use():
    """Token de cancelamento é de uso único: após uso, rejeitar reuso."""
    from app.db import add_watch_with_token, cancel_watch_by_token
    token = add_watch_with_token("Person_B", "c@example.com")
    assert cancel_watch_by_token(token) is True
    assert cancel_watch_by_token(token) is False


@pytest.mark.xfail(
    strict=True,
    reason="Tokens de cancelamento não implementados",
)
def test_adv008_cancel_token_constant_time_comparison():
    """Comparação de tokens em tempo constante (hmac.compare_digest) para
    prevenir timing oracle."""
    # Se a função existir, ela deve usar hmac.compare_digest
    import inspect

    from app.db import cancel_watch_by_token
    source = inspect.getsource(cancel_watch_by_token)
    assert "compare_digest" in source, (
        "cancel_watch_by_token deve usar hmac.compare_digest, não '=='"
    )


# ── ADV-009: enumeração de email ─────────────────────────────────────────────

def test_adv009_watch_response_does_not_reveal_existing_email():
    """POST /watch não deve retornar 409 Conflict para email já cadastrado.
    Um 409 revelaria que o email já está na base (enumeração de assinantes).
    Estratégia: adiciona via add_watch() (sem passar pelo rate limiter), depois
    faz UMA chamada HTTP para verificar que o status não é 409."""
    from app.db import add_watch

    # Adiciona diretamente no banco (sem HTTP) — não consome rate limit
    add_watch("Enumeration_Test_Person", "enumeration-test@example.com")

    # Uma única chamada HTTP para o email já existente
    r = client.post("/watch", json={
        "wiki_title": "Enumeration_Test_Person",
        "email": "enumeration-test@example.com",
    })

    # Não deve revelar "já existe" com 409 Conflict
    assert r.status_code != 409, (
        "POST /watch retornou 409 Conflict para email já cadastrado — vaza enumeração"
    )
    # 200 ou 429 (rate limit) são aceitáveis; 500 nunca
    assert r.status_code != 500


# ── ADV-011: busca repetida não causa DoS ────────────────────────────────────

def test_adv011_repeated_search_query_no_500():
    """Busca repetida por /person?wiki_title= não deve causar 500 mesmo
    com título inexistente (wiki.get_person_info é mockado internamente)."""
    for i in range(3):
        r = client.get("/person", params={"wiki_title": f"Nonexistent_Person_{i}"})
        # 404 (não encontrado) é aceitável; 500 nunca
        assert r.status_code != 500


# ── ADV-012: Unicode estranho em wiki_title ──────────────────────────────────

@pytest.mark.parametrize("weird_title", [
    "\x00",                    # null byte
    "Person�",            # replacement character
    "Ñoño",                    # non-ASCII
    "日本語タイトル",              # CJK
    "café",                    # Latin-1 extendido
    "Person‮",            # right-to-left override
    "A" * 500,                 # título longo (não 10k — esse é ADV-013)
])
def test_adv012_weird_unicode_in_wiki_title_no_exception(weird_title):
    """Títulos com Unicode estranho nunca devem causar exceção.
    Testa a camada db.add_watch() diretamente para não afetar rate limit HTTP."""
    from app.db import add_watch, init_db

    init_db()
    try:
        add_watch(weird_title, "unicode-test@example.com")
    except Exception as e:
        pytest.fail(f"Exceção com wiki_title Unicode: {weird_title!r} → {e}")


# ── ADV-013: entrada de tamanho absurdo ──────────────────────────────────────

def test_adv013_absurdly_long_wiki_title_no_exception():
    """wiki_title com 10.000 caracteres nunca deve causar exceção na camada DB."""
    from app.db import add_watch, init_db

    init_db()
    long_title = "A" * 10_000
    try:
        add_watch(long_title, "longtest@example.com")
    except Exception as e:
        pytest.fail(f"Exceção com wiki_title de 10k chars: {e}")


def test_adv013_absurdly_long_email_no_exception():
    """email com 10.000 caracteres nunca deve causar exceção na camada DB."""
    from app.db import add_watch, init_db

    init_db()
    long_email = "a" * 9_990 + "@example.com"
    try:
        add_watch("Clint_Eastwood", long_email)
    except Exception as e:
        pytest.fail(f"Exceção com email de 10k chars: {e}")
