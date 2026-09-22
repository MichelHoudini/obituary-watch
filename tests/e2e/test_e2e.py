"""
E2E tests: real browser (Playwright/Chromium) against a real uvicorn
process. See conftest.py for what's deliberately out of scope and why.
"""


def test_homepage_loads_with_no_console_errors(live_server, page):
    """Filters out third-party resource-loading noise (e.g. a CDN having a
    bad day, or a restrictive network blocking an external font) -- what
    actually matters here is JS errors thrown by our own code, which
    "pageerror" events capture distinctly from console.error spam about
    failed external resource fetches."""
    js_errors = []
    page.on("pageerror", lambda exc: js_errors.append(str(exc)))

    page.goto(live_server + "/")

    assert "mortivox" in page.title().lower()
    assert js_errors == [], f"JS errors on homepage: {js_errors}"


def test_homepage_has_working_trackevent_function(live_server, page):
    """trackEvent must exist and be callable in a real browser context --
    this is exactly what TestClient (used elsewhere in this suite)
    structurally cannot verify, since it never executes JS at all."""
    page.goto(live_server + "/")

    result = page.evaluate("typeof window.trackEvent")
    assert result == "function"

    # Calling it with no analytics configured must not throw.
    page.evaluate("window.trackEvent('test_event', {wiki_title: 'Test'})")


def test_no_analytics_script_when_unconfigured(live_server, page):
    """ANALYTICS_HEAD_SNIPPET is unset in the e2e test environment -- the
    page must render with no analytics tag at all, not a broken one."""
    page.goto(live_server + "/")

    html = page.content()
    assert "data-domain=" not in html
    assert "data-website-id=" not in html


def test_navigate_to_people_directory(live_server, page):
    page.goto(live_server + "/")
    page.click("a[href='/people']")

    page.wait_for_url("**/people")
    assert page.url.endswith("/people")


def test_person_page_renders_with_real_content(live_server, page):
    page.goto(live_server + "/person/clint-eastwood")

    assert "Clint Eastwood" in page.content()
    # The FAQ-style blocks added for SEO/copy clarity should be present.
    assert "being monitored" in page.content().lower()


def test_person_page_status_never_asserts_alive(live_server, page):
    """Regression guard for the copy decision made earlier in this
    project: never claim someone is alive with certainty, only that no
    death has been detected."""
    page.goto(live_server + "/person/clint-eastwood")

    text = page.content().lower()
    assert "is alive" not in text
    assert "has not detected a death update" in text


def test_deaths_log_page_renders(live_server, page):
    page.goto(live_server + "/deaths")
    assert "mortivox" in page.title().lower()


def test_no_python_traceback_visible_on_any_main_page(live_server, page):
    for path in ["/", "/people", "/deaths", "/person/clint-eastwood", "/lists/actors"]:
        page.goto(live_server + path)
        assert "Traceback (most recent call last)" not in page.content(), (
            f"Unhandled exception leaked into rendered HTML on {path}"
        )


def test_xss_safe_autocomplete_label(live_server, page):
    """Autocomplete labels must be rendered with textContent (not innerHTML).
    A malicious label like <img src=x onerror=window._xss=1> injected via a
    mocked Wikidata response must not execute as HTML."""
    js_errors = []
    page.on("pageerror", lambda exc: js_errors.append(str(exc)))

    page.goto(live_server + "/subscribe/filter")

    # Intercept the Wikidata API call and return a malicious label
    malicious_label = "<img src=x onerror=\"window._xss_fired=true\">"
    page.route(
        "**/wikidata.org/w/api.php*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=(
                '{"search":[{"id":"Q1","label":"'
                + malicious_label.replace('"', '\\"')
                + '","description":"test"}]}'
            ),
        ),
    )

    # Type in the occupation field to trigger the autocomplete
    page.fill("#occInput", "test")
    page.wait_for_timeout(500)  # debounce + fetch

    # The malicious label must have been rendered as plain text (textContent),
    # not as HTML — so the onerror handler must never have fired.
    xss_fired = page.evaluate("window._xss_fired")
    assert xss_fired is None or xss_fired is False, (
        "XSS payload executed! makeResultList uses innerHTML instead of textContent"
    )
    assert js_errors == [], f"Unexpected JS errors: {js_errors}"

    # The result item should appear but as plain text containing the literal < character
    # (verifying the content was inserted as text, not parsed as HTML)
    page.wait_for_selector("#occResults div", timeout=2000)
    result_text = page.inner_text("#occResults")
    assert "<img" in result_text, (
        "Malicious label must appear as plain text (with literal <), not as rendered HTML"
    )


def test_cancel_page_returns_200(live_server, page):
    """GET /cancel must return a confirmation page (200), not a 404.
    Email prefetch by clients must never accidentally cancel subscriptions."""
    page.goto(live_server + "/cancel?token=fake_test_token_xyz")
    assert page.url.endswith("/cancel?token=fake_test_token_xyz") or "/cancel" in page.url
    # Should be a 200 page with cancel-related content
    content = page.content().lower()
    assert "cancel" in content or "subscription" in content


def test_unsubscribe_page_returns_200(live_server, page):
    """/unsubscribe must return a usable form page, not a 404."""
    page.goto(live_server + "/unsubscribe")
    content = page.content().lower()
    assert "unsubscribe" in content or "subscription" in content
