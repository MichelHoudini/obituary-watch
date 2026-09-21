"""
Testes de integração para os endpoints de filtro de UI — PR 3.

Cobre: POST /watch com filtros, GET /api/filters/*, /subscribe/filter.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


# ── POST /watch com filtro de ocupação ──────────────────────────────────────

def test_watch_with_occupation_filter_accepted():
    """POST /watch com filter_occupation_qid válido deve retornar 200."""
    r = client.post("/watch", json={
        "wiki_title": "",
        "email": "occ@example.com",
        "filter_occupation_qid": "Q177220",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["filter_occupation_qid"] == "Q177220"


def test_watch_with_location_filter_accepted():
    """POST /watch com filter_location_qid válido deve retornar 200."""
    r = client.post("/watch", json={
        "wiki_title": "",
        "email": "loc@example.com",
        "filter_location_qid": "Q30",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["filter_location_qid"] == "Q30"


def test_watch_with_both_filters_accepted():
    """POST /watch com ambos os filtros preenchidos deve retornar 200."""
    r = client.post("/watch", json={
        "wiki_title": "",
        "email": "both@example.com",
        "filter_occupation_qid": "Q177220",
        "filter_location_qid": "Q30",
    })
    assert r.status_code == 200


def test_watch_empty_title_and_no_filters_rejected():
    """POST /watch sem wiki_title e sem filtros deve retornar 400."""
    r = client.post("/watch", json={
        "wiki_title": "",
        "email": "nobody@example.com",
    })
    assert r.status_code == 400


def test_watch_invalid_qid_format_rejected():
    """QID que não passa regex ^Q[0-9]+$ deve retornar 400."""
    r = client.post("/watch", json={
        "wiki_title": "",
        "email": "bad@example.com",
        "filter_occupation_qid": "q177220",  # lowercase — inválido
    })
    assert r.status_code == 400


def test_watch_qid_with_injection_rejected():
    """QID com SQL injection não deve passar na validação do regex."""
    r = client.post("/watch", json={
        "wiki_title": "",
        "email": "inj@example.com",
        "filter_occupation_qid": "Q1;DROP TABLE watches;--",
    })
    assert r.status_code == 400


# ── GET /api/filters/occupations ────────────────────────────────────────────

def test_filter_occupations_requires_q():
    """GET /api/filters/occupations sem ?q deve retornar 400."""
    r = client.get("/api/filters/occupations")
    assert r.status_code == 400


def test_filter_occupations_returns_results_shape():
    """GET /api/filters/occupations?q=musician retorna {results:[...]}."""
    mock_resp = [
        {"id": "Q177220", "label": "musician", "description": "person who creates music"},
    ]
    with patch("httpx.get") as mock_get:
        mock_get.return_value.json.return_value = {"search": mock_resp}
        mock_get.return_value.status_code = 200
        r = client.get("/api/filters/occupations?q=musician")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert isinstance(data["results"], list)
    if data["results"]:
        item = data["results"][0]
        assert "qid" in item
        assert "label" in item
        assert "description" in item


def test_filter_occupations_empty_q_returns_400():
    """q vazio deve retornar 400."""
    r = client.get("/api/filters/occupations?q=")
    assert r.status_code == 400


def test_filter_locations_returns_results_shape():
    """GET /api/filters/locations?q=brazil retorna {results:[...]}."""
    mock_resp = [
        {"id": "Q155", "label": "Brazil", "description": "country in South America"},
    ]
    with patch("httpx.get") as mock_get:
        mock_get.return_value.json.return_value = {"search": mock_resp}
        mock_get.return_value.status_code = 200
        r = client.get("/api/filters/locations?q=brazil")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data


def test_filter_wikidata_error_returns_empty():
    """Se Wikidata falhar (ex: IP bloqueado), retorna {results:[]}."""
    with patch("httpx.get", side_effect=Exception("connection refused")):
        r = client.get("/api/filters/occupations?q=musician")
    assert r.status_code == 200
    assert r.json() == {"results": []}


# ── GET /subscribe/filter ────────────────────────────────────────────────────

def test_subscribe_filter_page_returns_200():
    """A página /subscribe/filter deve retornar 200 com HTML."""
    r = client.get("/subscribe/filter")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


def test_subscribe_filter_page_has_form():
    """A página /subscribe/filter deve conter os campos de autocomplete."""
    r = client.get("/subscribe/filter")
    assert r.status_code == 200
    body = r.text
    assert "occInput" in body or "occQid" in body, "Campo de ocupação ausente"
    assert "locInput" in body or "locQid" in body, "Campo de localização ausente"
    assert "emailInput" in body, "Campo de email ausente"


def test_subscribe_filter_page_calls_wikidata_from_browser():
    """O JS da página deve chamar Wikidata com origin=* (client-side)."""
    r = client.get("/subscribe/filter")
    assert r.status_code == 200
    assert "wikidata.org" in r.text, "Link para Wikidata ausente no JS"
    assert "origin=*" in r.text, "origin=* ausente (necessário para cross-origin do browser)"
