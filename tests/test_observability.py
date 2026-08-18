"""
Tests for app/observability.py.
"""
import io
import json
import logging
import sys

from app.observability import setup_logging, setup_sentry


def test_setup_logging_produces_valid_json(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    setup_logging()
    # setup_logging captured the stdout reference at call time via
    # StreamHandler(sys.stdout); point it at our buffer directly too, since
    # monkeypatching sys.stdout after handler creation doesn't retarget it.
    logging.getLogger().handlers[0].stream = buf

    log = logging.getLogger("test.json")
    log.info("hello world")

    line = buf.getvalue().strip()
    parsed = json.loads(line)
    assert parsed["message"] == "hello world"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.json"
    assert "timestamp" in parsed


def test_setup_logging_includes_extra_fields():
    buf = io.StringIO()
    setup_logging()
    logging.getLogger().handlers[0].stream = buf

    log = logging.getLogger("test.extra")
    log.info("death detected", extra={"wiki_title": "Clint_Eastwood"})

    parsed = json.loads(buf.getvalue().strip())
    assert parsed["wiki_title"] == "Clint_Eastwood"


def test_setup_logging_does_not_leak_internal_record_attrs():
    """Fields like pathname/thread/process are logging internals, not
    application data -- they shouldn't clutter every JSON line."""
    buf = io.StringIO()
    setup_logging()
    logging.getLogger().handlers[0].stream = buf

    logging.getLogger("test.clean").info("plain message")

    parsed = json.loads(buf.getvalue().strip())
    assert "pathname" not in parsed
    assert "thread" not in parsed
    assert "process" not in parsed


def test_setup_sentry_without_dsn_is_a_complete_noop(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    sys.modules.pop("sentry_sdk", None)

    setup_sentry("test")

    assert "sentry_sdk" not in sys.modules


def test_setup_sentry_with_dsn_does_not_raise(monkeypatch):
    """A fake DSN must not crash the app on startup -- Sentry's SDK is
    designed to fail safe, and this pins that expectation for this
    codebase specifically."""
    monkeypatch.setenv("SENTRY_DSN", "https://fake@o0.ingest.sentry.io/0")
    setup_sentry("test")
