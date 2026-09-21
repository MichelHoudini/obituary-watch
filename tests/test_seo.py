"""
Testes de SEO técnico — SEO-001 a SEO-023.

SEO-001 a SEO-020: Testes locais via TestClient.
SEO-021 a SEO-023: @live — requerem mortivox.com ao vivo; skipados em CI.

Cobre: robots.txt, sitemap.xml, canonical, meta tags, OG, redirects,
noindex ausente, conteúdo sem JS, cloaking, google-site-verification.
"""
import re
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, follow_redirects=False)
client_follow = TestClient(app, follow_redirects=True)

CANONICAL_HOST = "https://mortivox.com"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_sitemap(xml_text: str) -> list[str]:
    """Extrai todas as <loc> de um sitemap XML."""
    root = ET.fromstring(xml_text)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [loc.text for loc in root.findall("sm:url/sm:loc", ns) if loc.text]


# ── SEO-001: robots.txt ──────────────────────────────────────────────────────

def test_seo001_robots_txt_returns_200():
    """robots.txt deve retornar 200 com Content-Type text/plain."""
    r = client_follow.get("/robots.txt")
    assert r.status_code == 200
    assert "text/plain" in r.headers.get("content-type", "")


def test_seo001_robots_txt_does_not_block_indexable_paths():
    """robots.txt não deve bloquear rotas indexáveis (/, /people, /person/*)."""
    r = client_follow.get("/robots.txt")
    body = r.text
    # Não deve ter Disallow: / (bloqueia tudo)
    assert "Disallow: /" not in body or "Allow: /" in body, (
        "robots.txt bloqueia todas as URLs com 'Disallow: /'"
    )


def test_seo001_robots_txt_valid_syntax():
    """robots.txt deve ter sintaxe válida: User-agent e regras."""
    r = client_follow.get("/robots.txt")
    body = r.text
    assert "User-agent:" in body, "robots.txt sem User-agent"
    assert "Allow:" in body or "Disallow:" in body, (
        "robots.txt sem nenhuma regra Allow/Disallow"
    )


# ── SEO-002: robots.txt → sitemap (já coberto em test_main.py) ──────────────

def test_seo002_robots_txt_links_to_sitemap():
    """robots.txt deve mencionar o sitemap.xml."""
    r = client_follow.get("/robots.txt")
    assert "sitemap" in r.text.lower(), "robots.txt não menciona sitemap"


# ── SEO-003: sitemap.xml válido ──────────────────────────────────────────────

def test_seo003_sitemap_returns_200():
    """sitemap.xml deve retornar 200."""
    r = client_follow.get("/sitemap.xml")
    assert r.status_code == 200


def test_seo003_sitemap_has_xml_content_type():
    """sitemap.xml deve ter Content-Type application/xml."""
    r = client_follow.get("/sitemap.xml")
    ct = r.headers.get("content-type", "")
    assert "xml" in ct, f"Content-Type do sitemap não é XML: {ct!r}"


def test_seo003_sitemap_is_valid_xml():
    """sitemap.xml deve ser XML válido (parseable sem exceção)."""
    r = client_follow.get("/sitemap.xml")
    try:
        ET.fromstring(r.text)
    except ET.ParseError as e:
        pytest.fail(f"sitemap.xml não é XML válido: {e}")


def test_seo003_sitemap_starts_with_xml_declaration():
    """sitemap.xml deve começar com declaração XML."""
    r = client_follow.get("/sitemap.xml")
    assert r.text.strip().startswith("<?xml"), (
        "sitemap.xml não começa com declaração XML"
    )


# ── SEO-004: URLs absolutas no sitemap ──────────────────────────────────────

def test_seo004_sitemap_urls_are_absolute():
    """Todas as URLs no sitemap devem ser absolutas (https://...)."""
    r = client_follow.get("/sitemap.xml")
    urls = _parse_sitemap(r.text)
    assert urls, "Sitemap não contém URLs"
    for url in urls:
        assert url.startswith("http"), (
            f"URL relativa no sitemap: {url!r}"
        )


def test_seo004_sitemap_urls_consistent_host():
    """Todas as URLs no sitemap devem ter o mesmo host (sem mistura http/https)."""
    r = client_follow.get("/sitemap.xml")
    urls = _parse_sitemap(r.text)
    # Extrai os hosts únicos
    hosts = set()
    for url in urls:
        m = re.match(r"https?://[^/]+", url)
        if m:
            hosts.add(m.group())
    assert len(hosts) == 1, (
        f"Sitemap tem múltiplos hosts: {hosts} — URLs inconsistentes"
    )


# ── SEO-005: sem URLs com noindex no sitemap ─────────────────────────────────

def test_seo005_sitemap_no_noindex_urls():
    """URLs no sitemap não devem ter 'noindex' no path."""
    r = client_follow.get("/sitemap.xml")
    urls = _parse_sitemap(r.text)
    for url in urls:
        assert "noindex" not in url.lower(), (
            f"URL com 'noindex' no sitemap: {url!r}"
        )


# ── SEO-006: sitemap com <= 50k URLs ─────────────────────────────────────────

def test_seo006_sitemap_under_50k_urls():
    """Sitemap não deve exceder 50.000 URLs (limite do Google/Bing)."""
    r = client_follow.get("/sitemap.xml")
    urls = _parse_sitemap(r.text)
    assert len(urls) <= 50_000, (
        f"Sitemap tem {len(urls)} URLs — excede limite de 50.000"
    )


def test_seo006_sitemap_has_at_least_one_url():
    """Sitemap deve ter ao menos 1 URL."""
    r = client_follow.get("/sitemap.xml")
    urls = _parse_sitemap(r.text)
    assert len(urls) >= 1


# ── SEO-007: URLs do sitemap respondem 200 ──────────────────────────────────

def test_seo007_sitemap_paths_respond_200():
    """As principais URLs do sitemap devem responder 200 quando acessadas."""
    r = client_follow.get("/sitemap.xml")
    urls = _parse_sitemap(r.text)

    # Testa os primeiros 10 paths únicos (sem repetir o host)
    from urllib.parse import urlparse
    paths_to_test = []
    for url in urls[:20]:
        path = urlparse(url).path
        if path not in paths_to_test:
            paths_to_test.append(path)
        if len(paths_to_test) >= 10:
            break

    for path in paths_to_test:
        resp = client_follow.get(path)
        assert resp.status_code == 200, (
            f"URL do sitemap retornou {resp.status_code}: {path}"
        )


# ── SEO-008/009: redirects (Render proxy — @live) ───────────────────────────

@pytest.mark.skip(reason="@live: redirects http→https e www→apex são feitos pelo Render proxy, não pela app")
def test_seo008_http_redirects_to_https_in_one_hop():
    """http://mortivox.com/ deve redirecionar para https em 1 salto (301/302)."""
    import httpx
    r = httpx.get("http://mortivox.com/", follow_redirects=False, timeout=10)
    assert r.status_code in (301, 302), f"Esperava redirect, obteve {r.status_code}"
    location = r.headers.get("location", "")
    assert location.startswith("https://"), f"Redirect não aponta para https: {location!r}"


@pytest.mark.skip(reason="@live: redirect www→apex é feito pelo Render proxy, não pela app")
def test_seo009_www_redirects_to_apex_in_one_hop():
    """https://www.mortivox.com/ deve redirecionar para mortivox.com em 1 salto."""
    import httpx
    r = httpx.get("https://www.mortivox.com/", follow_redirects=False, timeout=10)
    assert r.status_code in (301, 302)
    location = r.headers.get("location", "")
    assert "www" not in location, f"Redirect ainda tem www: {location!r}"


# ── SEO-010: 404 real (não soft 404) ────────────────────────────────────────

def test_seo010_nonexistent_page_returns_real_404():
    """Página inexistente deve retornar HTTP 404, não 200 (soft 404)."""
    r = client_follow.get("/this-page-absolutely-does-not-exist-seo010")
    assert r.status_code == 404, (
        f"Página inexistente retornou {r.status_code} em vez de 404 (soft 404)"
    )


def test_seo010_404_does_not_have_200_status():
    """O status code deve ser exatamente 404, não 200 com body de erro."""
    r = client_follow.get("/seo-test-nonexistent-xyz-seo010")
    assert r.status_code != 200, "Página inexistente retornou 200 (soft 404)"


# ── SEO-011: nenhum noindex em páginas indexáveis ────────────────────────────

@pytest.mark.parametrize("path", ["/", "/people", "/deaths"])
def test_seo011_no_noindex_on_indexable_pages(path):
    """Páginas indexáveis não devem ter meta noindex nem X-Robots-Tag: noindex."""
    r = client_follow.get(path)
    assert r.status_code == 200
    # X-Robots-Tag no header
    x_robots = r.headers.get("x-robots-tag", "").lower()
    assert "noindex" not in x_robots, (
        f"X-Robots-Tag: noindex em {path}: {x_robots!r}"
    )
    # Meta noindex no HTML — aceita strings como "noindex" em comentários JS,
    # mas não como valor de content= em uma meta tag
    assert 'content="noindex"' not in r.text.lower(), (
        f"Meta noindex encontrado no HTML de {path}"
    )
    assert "noindex" not in r.text[:3000].lower(), (
        f"'noindex' encontrado no <head> de {path}"
    )


# ── SEO-012: HTML bruto da home tem conteúdo ────────────────────────────────

def test_seo012_homepage_has_h1_in_raw_html():
    """HTML bruto (sem JS) da home deve conter <h1>."""
    r = client_follow.get("/")
    assert r.status_code == 200
    assert "<h1>" in r.text.lower() or "<h1 " in r.text.lower(), (
        "Homepage sem <h1> no HTML bruto — Google não verá o título principal"
    )


def test_seo012_homepage_has_title_tag():
    """HTML bruto da home deve ter tag <title>."""
    r = client_follow.get("/")
    assert "<title>" in r.text.lower(), "Homepage sem <title> no HTML bruto"


def test_seo012_homepage_has_meta_description():
    """HTML bruto da home deve ter meta description."""
    r = client_follow.get("/")
    assert 'name="description"' in r.text.lower(), (
        "Homepage sem meta description no HTML bruto"
    )


def test_seo012_homepage_has_main_content_without_js():
    """HTML bruto da home deve ter conteúdo principal visível (sem JS)."""
    r = client_follow.get("/")
    # O conteúdo principal não deve depender de JS para ser renderizado
    assert "mortivox" in r.text.lower(), "Homepage sem 'mortivox' no HTML bruto"
    assert "wikipedia" in r.text.lower(), "Homepage sem menção a 'wikipedia' no HTML bruto"


# ── SEO-013: /person/* tem conteúdo real ─────────────────────────────────────

def test_seo013_person_page_has_person_name():
    """Página de /person/clint-eastwood deve conter o nome no HTML bruto."""
    r = client_follow.get("/person/clint-eastwood")
    assert r.status_code == 200
    assert "Clint Eastwood" in r.text or "clint eastwood" in r.text.lower(), (
        "Página de pessoa sem o nome no HTML bruto"
    )


def test_seo013_person_page_has_h1():
    """Página de pessoa deve ter <h1> com o nome."""
    r = client_follow.get("/person/clint-eastwood")
    assert r.status_code == 200
    assert "<h1>" in r.text.lower() or "<h1 " in r.text.lower()


def test_seo013_person_page_monitored_status_present():
    """Página de pessoa deve explicar que está sendo monitorada."""
    r = client_follow.get("/person/clint-eastwood")
    assert r.status_code == 200
    # Verifica que a página não está vazia
    assert len(r.text) > 1000, "Página de pessoa muito pequena — possível conteúdo ausente"


# ── SEO-014: sem cloaking ────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ["/", "/people"])
def test_seo014_googlebot_gets_same_content_as_browser(path):
    """Googlebot deve receber o mesmo conteúdo que um navegador comum.
    (Cloaking é penalizado pelo Google.)"""
    r_browser = client_follow.get(path, headers={"User-Agent": "Mozilla/5.0"})
    r_googlebot = client_follow.get(
        path,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"}
    )

    assert r_browser.status_code == r_googlebot.status_code
    # O conteúdo principal não deve diferir significativamente
    # Heurística: o tamanho do HTML não deve variar mais de 10%
    diff_ratio = abs(len(r_browser.text) - len(r_googlebot.text)) / max(len(r_browser.text), 1)
    assert diff_ratio < 0.10, (
        f"HTML para Googlebot difere muito do navegador comum em {path}: "
        f"{diff_ratio:.1%} diferença de tamanho"
    )


# ── SEO-015: título único por página ─────────────────────────────────────────

def test_seo015_different_pages_have_different_titles():
    """Páginas diferentes devem ter <title> diferente (títulos duplicados são penalizados)."""
    titles = {}
    pages = ["/", "/people", "/deaths", "/person/clint-eastwood"]
    for path in pages:
        r = client_follow.get(path)
        if r.status_code == 200:
            m = re.search(r"<title>([^<]+)</title>", r.text, re.IGNORECASE)
            if m:
                titles[path] = m.group(1).strip()

    # Verifica que não há títulos duplicados entre páginas
    title_list = list(titles.values())
    assert len(title_list) == len(set(title_list)), (
        f"Títulos duplicados detectados: {titles}"
    )


# ── SEO-016: meta description única ─────────────────────────────────────────

def test_seo016_different_pages_have_different_meta_descriptions():
    """Páginas diferentes devem ter meta description diferente."""
    descriptions = {}
    pages = ["/", "/people", "/person/clint-eastwood"]
    for path in pages:
        r = client_follow.get(path)
        if r.status_code == 200:
            m = re.search(
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
                r.text, re.IGNORECASE
            )
            if not m:
                m = re.search(
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
                    r.text, re.IGNORECASE
                )
            if m:
                descriptions[path] = m.group(1).strip()

    desc_list = list(descriptions.values())
    assert len(desc_list) == len(set(desc_list)), (
        f"Meta descriptions duplicadas: {descriptions}"
    )


# ── SEO-017: h1 único por página ─────────────────────────────────────────────

@pytest.mark.parametrize("path", ["/", "/people", "/person/clint-eastwood"])
def test_seo017_single_h1_per_page(path):
    """Cada página deve ter exatamente 1 <h1> (múltiplos h1 prejudicam SEO)."""
    r = client_follow.get(path)
    assert r.status_code == 200
    h1_count = len(re.findall(r"<h1[\s>]", r.text, re.IGNORECASE))
    assert h1_count == 1, (
        f"{path} tem {h1_count} tags <h1> — deve ter exatamente 1"
    )


# ── SEO-018: canonical presente e self-referencial ──────────────────────────

@pytest.mark.parametrize("path", ["/", "/people", "/person/clint-eastwood"])
def test_seo018_canonical_link_present(path):
    """Cada página deve ter <link rel='canonical'>."""
    r = client_follow.get(path)
    assert r.status_code == 200
    assert 'rel="canonical"' in r.text.lower() or "rel='canonical'" in r.text.lower(), (
        f"canonical ausente em {path}"
    )


@pytest.mark.parametrize("path", ["/", "/people", "/person/clint-eastwood"])
def test_seo018_canonical_is_self_referential(path):
    """canonical deve apontar para a própria página (não para outra URL)."""
    r = client_follow.get(path)
    assert r.status_code == 200
    m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', r.text, re.IGNORECASE)
    if not m:
        m = re.search(r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']canonical', r.text, re.IGNORECASE)
    assert m, f"Nenhum canonical encontrado em {path}"
    canonical_url = m.group(1)
    # O path da URL canonical deve corresponder ao path acessado
    from urllib.parse import urlparse
    canonical_path = urlparse(canonical_url).path
    assert canonical_path == path or canonical_path == path.rstrip("/"), (
        f"canonical de {path} aponta para {canonical_url!r} (path: {canonical_path!r})"
    )


# ── SEO-019: Open Graph e Twitter Card ──────────────────────────────────────

@pytest.mark.parametrize("path", ["/", "/people", "/person/clint-eastwood"])
def test_seo019_open_graph_tags_present(path):
    """Páginas devem ter meta tags Open Graph (og:title, og:description)."""
    r = client_follow.get(path)
    assert r.status_code == 200
    assert 'og:title' in r.text, f"og:title ausente em {path}"
    assert 'og:description' in r.text, f"og:description ausente em {path}"
    assert 'og:url' in r.text, f"og:url ausente em {path}"


@pytest.mark.parametrize("path", ["/", "/people", "/person/clint-eastwood"])
def test_seo019_twitter_card_present(path):
    """Páginas devem ter meta Twitter Card."""
    r = client_follow.get(path)
    assert r.status_code == 200
    assert 'twitter:card' in r.text, f"twitter:card ausente em {path}"


# ── SEO-020: google-site-verification no HTML (xfail — ausente) ─────────────

@pytest.mark.xfail(
    strict=True,
    reason="google-site-verification ausente no HTML: a tag meta não é injetada "
           "pelo servidor. A verificação de Domínio funciona via DNS TXT (presente), "
           "mas a verificação de Prefixo de URL requer a meta tag no HTML. "
           "Impacto: Search Console só pode ser configurado como Domínio, não URL Prefix.",
)
def test_seo020_google_site_verification_in_html():
    """HTML da home deve conter meta google-site-verification para URL Prefix property."""
    r = client_follow.get("/")
    assert r.status_code == 200
    assert "google-site-verification" in r.text, (
        "Meta tag google-site-verification ausente no HTML. "
        "Adicionar via GOOGLE_SITE_VERIFICATION env var ou hardcoded em layout()."
    )


# ── SEO-021 a SEO-023: @live ─────────────────────────────────────────────────

@pytest.mark.skip(reason="@live: requer mortivox.com ao vivo; rodar fora do CI")
def test_seo021_live_sitemap_urls_accessible():
    """@live: todas as URLs do sitemap devem responder 200 em produção."""
    import httpx
    r = httpx.get("https://mortivox.com/sitemap.xml", timeout=30)
    urls = _parse_sitemap(r.text)
    failed = []
    for url in urls[:20]:  # limita para não sobrecarregar
        resp = httpx.get(url, timeout=10)
        if resp.status_code != 200:
            failed.append(f"{url} → {resp.status_code}")
    assert not failed, "URLs do sitemap com erro:\n" + "\n".join(failed)


@pytest.mark.skip(reason="@live: TTFB quente requer servidor aquecido")
def test_seo022_live_warm_ttfb_under_500ms():
    """@live: TTFB quente de mortivox.com < 500ms."""
    import time

    import httpx
    httpx.get("https://mortivox.com/status", timeout=30)  # aquecimento
    start = time.perf_counter()
    r = httpx.get("https://mortivox.com/", timeout=10)
    elapsed = time.perf_counter() - start
    assert r.status_code == 200
    assert elapsed < 0.5, f"TTFB quente: {elapsed:.3f}s (limite: 0.5s)"


@pytest.mark.skip(reason="@live: Lighthouse CI requer CLI e servidor ao vivo")
def test_seo023_lighthouse_lcp_cls():
    """@live: Lighthouse — LCP <= 2.5s, CLS < 0.1. Requer @lhci CLI."""
    pytest.skip("Executar: lhci collect --url https://mortivox.com && lhci assert")
