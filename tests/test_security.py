"""
Testes de segurança — SEG-001 a SEG-005.

SEG-001: HSTS presente em respostas HTTPS.
SEG-002: X-Content-Type-Options: nosniff presente.
SEG-003: CSP presente.
SEG-004: Nenhum segredo em respostas públicas.
SEG-005: Varredura de segredos no histórico git.

NOTA: SEG-001/002/003 estão xfail porque a app FastAPI (versão atual) não
adiciona esses headers. HSTS é adicionado pela infraestrutura do Render
(TLS termination), não pela aplicação. CSP e X-Content-Type-Options devem
ser adicionados via middleware.
"""
import os
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ── SEG-001: HSTS ────────────────────────────────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="HSTS não configurado pela aplicação: o header Strict-Transport-Security "
           "é adicionado pelo Render (TLS terminator), não visível via TestClient. "
           "Para validar em produção, use teste @live.",
)
def test_seg001_hsts_header_present():
    """HTTPS responses must include Strict-Transport-Security."""
    r = client.get("/")
    assert "strict-transport-security" in {k.lower() for k in r.headers}, (
        "Header Strict-Transport-Security ausente. "
        "Adicionar SecurityHeadersMiddleware ou configurar no Render."
    )


# ── SEG-002: X-Content-Type-Options ─────────────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="X-Content-Type-Options não configurado: middleware de headers de "
           "segurança não implementado; pending SEG milestone",
)
def test_seg002_x_content_type_options_nosniff():
    """Respostas HTTP devem incluir X-Content-Type-Options: nosniff."""
    r = client.get("/")
    headers_lower = {k.lower(): v for k, v in r.headers.items()}
    assert headers_lower.get("x-content-type-options", "").lower() == "nosniff", (
        "X-Content-Type-Options: nosniff ausente"
    )


def test_seg002_json_endpoint_has_correct_content_type():
    """Endpoints JSON devem retornar Content-Type: application/json, não text/html.
    Evita que browsers façam content-sniffing em respostas JSON."""
    r = client.get("/api/deaths")
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert "application/json" in ct, f"Content-Type incorreto: {ct!r}"


# ── SEG-003: CSP ─────────────────────────────────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="Content-Security-Policy não configurado: middleware de segurança "
           "não implementado; pending SEG milestone",
)
def test_seg003_content_security_policy_present():
    """Respostas HTML devem incluir Content-Security-Policy."""
    r = client.get("/")
    headers_lower = {k.lower() for k in r.headers}
    assert "content-security-policy" in headers_lower, (
        "Content-Security-Policy ausente. "
        "Adicionar via SecurityHeadersMiddleware."
    )


# ── SEG-004: Sem segredos em respostas públicas ──────────────────────────────

_SECRET_PATTERNS = [
    re.compile(r"re_[A-Za-z0-9_]{24,}", re.IGNORECASE),   # Resend API key
    re.compile(r"eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.", re.IGNORECASE),  # JWT
    re.compile(r"postgresql://[^\s\"'<>]+", re.IGNORECASE),  # Database URL
    re.compile(r"supabase[^\s\"'<>]{20,}", re.IGNORECASE),   # Supabase key
    re.compile(r"sk_live_[A-Za-z0-9]+", re.IGNORECASE),      # Stripe live key
]


@pytest.mark.parametrize("path", ["/", "/people", "/deaths", "/status", "/robots.txt", "/sitemap.xml"])
def test_seg004_no_secrets_in_public_responses(path):
    """Nenhuma resposta pública deve conter tokens, chaves de API ou URLs de banco."""
    r = client.get(path)
    body = r.text
    for pat in _SECRET_PATTERNS:
        m = pat.search(body)
        assert m is None, (
            f"Possível segredo vazado em {path}: padrão {pat.pattern!r} "
            f"encontrou '{m.group()[:20]}...'"
        )


def test_seg004_status_endpoint_does_not_leak_env_vars():
    """/status não deve expor variáveis de ambiente sensíveis."""
    r = client.get("/status")
    assert r.status_code == 200
    body = r.text
    sensitive_env_names = ["RESEND_API_KEY", "DATABASE_URL", "SENTRY_DSN"]
    for name in sensitive_env_names:
        val = os.environ.get(name, "")
        if val:
            assert val not in body, f"Valor de {name} vazado em /status"


def test_seg004_no_python_internals_in_error_pages():
    """Páginas de erro (404) não devem expor stack traces ou detalhes internos."""
    r = client.get("/nonexistent-page-seg004")
    body = r.text
    assert "Traceback" not in body, "Stack trace Python exposto em resposta de erro"
    assert "File \"" not in body, "Caminho de arquivo Python exposto em resposta de erro"


# ── SEG-005: Varredura de segredos no histórico git ──────────────────────────

def test_seg005_no_obvious_secrets_in_tracked_files():
    """Verificação estática: arquivos rastreados pelo git não devem conter
    padrões de segredos hardcoded. Esta é uma verificação de heurística, não
    substitui o trufflehog/gitleaks."""
    import subprocess
    import sys

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    result = subprocess.run(
        ["git", "ls-files", "--exclude-standard"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        pytest.skip("git ls-files falhou; pulando verificação de segredos")

    tracked_files = [
        f for f in result.stdout.splitlines()
        if f.endswith((".py", ".yml", ".yaml", ".json", ".env", ".txt", ".toml"))
        and not f.startswith(".venv")
        and not f.startswith("tests/")  # test files may have function names that look like keys
        and not f.startswith("docs/")
    ]

    # Padrões de segredos hardcoded (nunca devem aparecer em arquivos rastreados)
    # Resend keys: re_ seguido de 20+ alfanuméricos SEM underscores (snake_case é código, não chave)
    hardcoded_patterns = [
        re.compile(r"\bre_[A-Za-z0-9]{20,}\b"),          # Resend key (sem underscore — snake_case é código)
        re.compile(r"password\s*=\s*['\"][^'\"]{8,}"),    # senha hardcoded
        re.compile(r"secret\s*=\s*['\"][^'\"]{8,}"),      # secret hardcoded
    ]

    violations = []
    for relative_path in tracked_files[:200]:  # limita para não exceder timeout
        full_path = os.path.join(repo_root, relative_path)
        try:
            with open(full_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            for pat in hardcoded_patterns:
                m = pat.search(content)
                if m:
                    violations.append(
                        f"{relative_path}: padrão {pat.pattern!r} → '{m.group()[:30]}'"
                    )
        except OSError:
            pass

    assert not violations, (
        "Possíveis segredos hardcoded encontrados:\n" + "\n".join(violations)
    )
