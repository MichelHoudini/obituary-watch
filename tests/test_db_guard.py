"""
Tests for the test-database safety guard (tests/db_guard.py).

ADV-015: a URL with a remote host must be rejected before any write.
"""
import os

import pytest


def test_guard_rejects_remote_host():
    """URL pointing to a remote host (e.g. Supabase) is rejected."""
    from db_guard import assert_test_db_safe
    with pytest.raises(RuntimeError, match="SAFETY ABORT"):
        assert_test_db_safe("postgresql://user:pass@db.abc.supabase.co:5432/postgres")


def test_guard_rejects_local_db_without_test_in_name():
    """localhost but database name does not contain 'test' is rejected."""
    from db_guard import assert_test_db_safe
    with pytest.raises(RuntimeError, match="SAFETY ABORT"):
        assert_test_db_safe("postgresql://user:pass@localhost:5432/myapp_production")


def test_guard_accepts_localhost_with_test_db():
    """localhost + 'test' in db name is accepted."""
    from db_guard import assert_test_db_safe
    assert_test_db_safe("postgresql://user:pass@localhost:5432/mortivox_test")


def test_guard_accepts_loopback_with_test_db():
    """127.0.0.1 + 'test' in db name is accepted."""
    from db_guard import assert_test_db_safe
    assert_test_db_safe("postgresql://user:pass@127.0.0.1:5432/test_db")


def test_resolve_prefers_test_database_url(monkeypatch):
    """TEST_DATABASE_URL takes precedence over DATABASE_URL."""
    from db_guard import resolve_test_db_url
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://localhost:5432/explicit_test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db.supabase.co:5432/prod")
    assert resolve_test_db_url() == "postgresql://localhost:5432/explicit_test"


def test_resolve_falls_back_to_database_url_in_ci(monkeypatch):
    """In CI (CI=true), DATABASE_URL is used when TEST_DATABASE_URL is absent."""
    from db_guard import resolve_test_db_url
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/mortivox_test")
    monkeypatch.setenv("CI", "true")
    assert resolve_test_db_url() == "postgresql://localhost:5432/mortivox_test"


def test_resolve_returns_none_outside_ci_without_test_url(monkeypatch):
    """Outside CI and no TEST_DATABASE_URL → None (use SQLite)."""
    from db_guard import resolve_test_db_url
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("CI", "false")
    assert resolve_test_db_url() is None
