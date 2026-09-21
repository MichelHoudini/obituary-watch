"""
dates.py — Death-date parsing and formatting helpers.

Shared by main.py (HTML display) and email.py (email body).
Kept separate to avoid the circular import that would result from
email.py importing from main.py (which already imports from email.py).
"""

import re
from datetime import date

_MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"]


def _parse_death_date(raw: str | None) -> date | None:
    """Extract just the date from a {{Death date...}} wikitext value."""
    if not raw:
        return None
    match = re.search(
        r"\{\{\s*[Dd]eath date(?: and age)?\s*\|\s*(\d{4})\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})",
        raw,
    )
    if not match:
        return None
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def format_death_date(raw: str | None) -> str:
    """Turn a {{Death date...}} wikitext value into 'Month D, YYYY'.

    Falls back to the raw value if it doesn't match the template shape,
    so nothing is ever silently hidden — just formatted when possible."""
    if not raw:
        return "confirmed"
    parsed = _parse_death_date(raw)
    if parsed is not None:
        return f"{_MONTH_NAMES[parsed.month]} {parsed.day}, {parsed.year}"
    return raw


def format_death_date_for_email(raw: str | None) -> str:
    """Format death date for use in email body.

    Stricter than format_death_date: placeholder HTML comments and
    unrecognised wikitext templates become a human-friendly fallback
    instead of being passed through verbatim to the email reader."""
    if not raw:
        return "Date not yet confirmed on Wikipedia"

    # Strip HTML comments (e.g. the boilerplate placeholder comment)
    stripped = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL).strip()

    # Placeholder or empty after stripping comments
    if not stripped or "YYYY" in stripped:
        return "Date not yet confirmed on Wikipedia"

    parsed = _parse_death_date(stripped)
    if parsed is not None:
        return f"{_MONTH_NAMES[parsed.month]} {parsed.day}, {parsed.year}"

    # Any remaining wikitext template that couldn't be parsed → fallback
    if "{{" in stripped:
        return "Date not yet confirmed on Wikipedia"

    return stripped
