"""
Tests for app/watcher.py's extract_death_date().

Covers the exact false-positive this function was written to fix: Wikipedia's
Person infobox commonly carries this literal placeholder comment in the
death_date field, even on living people's pages:

    <!-- {{Death date and age|YYYY|MM|DD|YYYY|MM|DD}} (DEATH date then BIRTH date) -->

A naive "field is non-empty" check accepts that as a real date. This
regressed once already in production (the Clint Eastwood false positive,
August 2026) so these tests exist to make sure it can't regress silently
again.
"""
from app.watcher import extract_death_date


def _wrap_infobox(death_date_field: str) -> str:
    return f"""
{{{{Infobox person
|name = Test Person
|birth_date = {{{{Birth date and age|1930|5|31}}}}
|death_date = {death_date_field}
|death_place =
|occupation = Actor
}}}}
"""


def test_rejects_the_placeholder_comment():
    """The exact false-positive pattern that shipped to production once."""
    wikitext = _wrap_infobox(
        "<!-- {{Death date and age|YYYY|MM|DD|YYYY|MM|DD}} "
        "(DEATH date then BIRTH date) -->"
    )
    assert extract_death_date(wikitext) is None


def test_accepts_a_real_filled_in_date():
    wikitext = _wrap_infobox("{{Death date and age|2026|7|20|1930|5|31}}")
    result = extract_death_date(wikitext)
    assert result is not None
    assert "2026" in result


def test_accepts_real_date_even_with_trailing_comment():
    """A real date can still carry an unrelated trailing comment (e.g. an
    editor note about a source) -- the digits outside the comment should
    still be picked up."""
    wikitext = _wrap_infobox(
        "{{Death date and age|2026|7|20|1930|5|31}}<!-- per obituary in NYT -->"
    )
    result = extract_death_date(wikitext)
    assert result is not None
    assert "2026" in result


def test_missing_death_date_field_returns_none():
    wikitext = """
{{Infobox person
|name = Someone Alive
|birth_date = {{Birth date and age|1990|1|1}}
}}
"""
    assert extract_death_date(wikitext) is None


def test_empty_death_date_field_returns_none():
    wikitext = _wrap_infobox("")
    assert extract_death_date(wikitext) is None


def test_not_an_infobox_template_is_ignored():
    """A death_date-shaped field on some unrelated template shouldn't be
    picked up -- only the Person infobox is watched."""
    wikitext = """
{{Some other template
|death_date = {{Death date and age|2026|7|20|1930|5|31}}
}}
"""
    assert extract_death_date(wikitext) is None


def test_malformed_wikitext_does_not_raise():
    """extract_death_date must never crash the watcher loop on weird input --
    it should degrade to None, not throw."""
    assert extract_death_date("{{{{{{not valid wikitext at all") is None
