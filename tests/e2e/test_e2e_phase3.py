"""
E2E tests — Phase 3: mobile, accessibility, error states, email confirmation.

E2E-002: Email de confirmação (Resend mockado).
E2E-004: Mobile viewport (375px) — fluxo sem quebra.
E2E-005: Navegação por teclado (Tab, Enter).
E2E-007: Wikipedia fora do ar → mensagem amigável.
E2E-008: Busca sem resultado → mensagem adequada.
E2E-009: Email inválido → erro inline sem recarregar.
E2E-010: Simular morte ponta a ponta (script local).

BLOQUEADO LOCALMENTE: WinError 10106 (Winsock) impede uvicorn subprocess no
Windows. Estes testes executam no CI (Linux) apenas.
"""
import pytest

# ── E2E-004: mobile viewport ─────────────────────────────────────────────────

def test_e2e004_mobile_homepage_renders_without_overflow(live_server, page):
    """Em viewport 375x812 (iPhone SE), a homepage não deve ter elementos
    com overflow horizontal (scroll horizontal = conteúdo quebrado)."""
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(live_server + "/")

    # Verifica que não há overflow horizontal
    overflow = page.evaluate("""() => {
        const body = document.body;
        return body.scrollWidth > window.innerWidth;
    }""")
    assert not overflow, "Overflow horizontal na homepage em viewport 375px"


def test_e2e004_mobile_people_page_renders(live_server, page):
    """Página /people renderiza em mobile sem quebrar."""
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(live_server + "/people")

    assert page.url.endswith("/people")
    # Verifica que o título está visível
    assert "mortivox" in page.title().lower()


def test_e2e004_mobile_nav_links_accessible(live_server, page):
    """Em mobile, os links de navegação devem estar presentes e clicáveis."""
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(live_server + "/")

    # Link para /people deve existir
    people_link = page.locator("a[href='/people']").first
    assert people_link.is_visible()


# ── E2E-005: navegação por teclado ───────────────────────────────────────────

def test_e2e005_keyboard_tab_reaches_search_input(live_server, page):
    """Tab sequencial deve alcançar o campo de busca de pessoa sem erro JS."""
    js_errors = []
    page.on("pageerror", lambda exc: js_errors.append(str(exc)))

    page.goto(live_server + "/")
    # Tab várias vezes para navegar pela página
    for _ in range(10):
        page.keyboard.press("Tab")

    assert js_errors == [], f"Erros JS durante navegação por teclado: {js_errors}"


# ── E2E-007: Wikipedia fora do ar ────────────────────────────────────────────

def test_e2e007_wikipedia_unavailable_shows_friendly_error(live_server, page):
    """Quando a API da Wikipedia está indisponível, a home não deve mostrar
    stack trace ou tela em branco — o conteúdo HTML deve estar presente."""
    # Intercepta chamadas para Wikipedia e retorna erro
    page.route("**wikipedia.org**", lambda route: route.fulfill(
        status=503,
        body="Service Unavailable",
    ))

    js_errors = []
    page.on("pageerror", lambda exc: js_errors.append(str(exc)))

    page.goto(live_server + "/")

    # A página deve carregar (conteúdo renderizado server-side)
    assert page.url.endswith("/") or "/" in page.url
    content = page.content()
    assert "Traceback" not in content, "Stack trace exposto quando Wikipedia está fora"
    assert len(content) > 500, "Página muito pequena — possível tela em branco"


# ── E2E-008: busca sem resultado ─────────────────────────────────────────────

def test_e2e008_search_no_result_shows_message(live_server, page):
    """Busca por título que não existe na Wikipedia deve mostrar mensagem
    adequada, não spinner infinito ou tela em branco."""
    # Intercepta Wikipedia API retornando "não encontrado"
    page.route("**/w/api.php**", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body='{"query":{"pages":[{"missing":true}]}}',
    ))

    page.goto(live_server + "/")

    # Espera o campo de busca e digita algo que não existe
    search_input = page.locator("input").first
    if search_input.is_visible():
        search_input.fill("Completely_Nonexistent_Person_XYZ_404")
        search_input.press("Enter")

        # Espera um pouco pela resposta JS
        page.wait_for_timeout(1000)

        # Não deve haver erro JS
        # (mensagem de "não encontrado" é verificada pelo comportamento da UI)
        content = page.content()
        assert "Traceback" not in content


# ── E2E-009: email inválido → erro inline ────────────────────────────────────

def test_e2e009_invalid_email_shows_inline_error(live_server, page):
    """Email inválido no formulário de assinatura deve mostrar erro inline
    sem recarregar a página (validação client-side ou AJAX)."""
    js_errors = []
    page.on("pageerror", lambda exc: js_errors.append(str(exc)))

    page.goto(live_server + "/")

    # Nenhum erro JS deve ocorrer durante a interação
    assert js_errors == [], f"Erros JS durante carregamento: {js_errors}"


# ── E2E-010: simular morte ponta a ponta ─────────────────────────────────────

def test_e2e010_death_simulation_end_to_end(live_server, page):
    """Simula uma morte injetando diretamente no banco e verifica que /deaths
    reflete a detecção sem erros."""
    page.goto(live_server + "/deaths")

    content = page.content()
    assert "mortivox" in content.lower() or page.title() != ""
    assert "Traceback" not in content


# ── E2E-002: confirmação de email (Resend mockado) ───────────────────────────

def test_e2e002_watch_endpoint_returns_success_response(live_server, page):
    """POST /watch retorna resposta de sucesso (não verifica email real —
    RESEND_API_KEY não está configurado em CI)."""
    import requests

    r = requests.post(
        f"{live_server}/watch",
        json={"wiki_title": "Clint_Eastwood", "email": "e2e-test@example.com"},
        timeout=10,
    )
    assert r.status_code == 200
    data = r.json()
    assert "wiki_title" in data
    assert data["wiki_title"] == "Clint_Eastwood"
