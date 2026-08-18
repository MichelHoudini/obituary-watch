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
