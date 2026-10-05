"""URL 校验与正文清洗单测。"""
import pytest

from app.core.llm import LLMError
from app.services import fetcher


def test_validate_https_ok():
    assert fetcher.validate_url("https://example.com/a") == "https://example.com/a"


def test_validate_http_ok():
    assert fetcher.validate_url("http://example.com") == "http://example.com"


def test_validate_reject_non_http():
    with pytest.raises(LLMError) as e:
        fetcher.validate_url("ftp://example.com")
    assert e.value.code == "INVALID_URL"


def test_validate_reject_localhost():
    with pytest.raises(LLMError) as e:
        fetcher.validate_url("http://localhost:8000")
    assert e.value.code == "INVALID_URL"


def test_clean_text_strips_script():
    from bs4 import BeautifulSoup
    html = "<html><body><script>alert(1)</script><p>正文内容</p></body></html>"
    text = fetcher._clean_text(BeautifulSoup(html, "html.parser"))
    assert "正文内容" in text
    assert "alert" not in text


@pytest.mark.parametrize("url", ["http://192.168.1.1", "http://10.0.0.1", "http://169.254.169.254", "http://[fc00::1]", "http://127.1.2.3", "http://user:pass@example.com"])
def test_reject_private_addresses_and_credentials(url):
    with pytest.raises(LLMError):
        fetcher.validate_url(url)


@pytest.mark.asyncio
async def test_reject_domain_resolving_to_private_ip(monkeypatch):
    monkeypatch.setattr(fetcher.socket, "getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("10.0.0.1", 80))])
    with pytest.raises(LLMError) as exc:
        await fetcher._check_public_host("https://example.com")
    assert exc.value.code == "INVALID_URL"


@pytest.mark.asyncio
async def test_redirect_to_private_address_rejected(monkeypatch):
    import httpx
    checked = []
    async def public_host(url):
        checked.append(url)
        return "93.184.216.34"
    monkeypatch.setattr(fetcher, "_check_public_host", public_host)
    client_type = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"}))
    monkeypatch.setattr(fetcher.httpx, "AsyncClient", lambda **kwargs: client_type(transport=transport, **kwargs))
    with pytest.raises(LLMError) as exc:
        await fetcher.fetch_response("https://example.com")
    assert exc.value.code == "INVALID_URL"
    assert checked == ["https://example.com"]


@pytest.mark.asyncio
async def test_rss_uses_checked_fetcher(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services import sources
    safe_fetch = AsyncMock(side_effect=LLMError("INVALID_URL", "blocked"))
    monkeypatch.setattr(fetcher, "fetch_response", safe_fetch)
    with pytest.raises(LLMError):
        await sources._fetch_rss(None, SimpleNamespace(url="http://10.0.0.1"), "u")
    safe_fetch.assert_awaited_once_with("http://10.0.0.1")


@pytest.mark.asyncio
async def test_connection_pins_checked_ip_and_preserves_host_and_tls(monkeypatch):
    import httpx
    async def public_host(url):
        return "93.184.216.34"
    monkeypatch.setattr(fetcher, "_check_public_host", public_host)
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, content=b"safe")
    client_type = httpx.AsyncClient
    monkeypatch.setattr(fetcher.httpx, "AsyncClient", lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs))
    response = await fetcher.fetch_response("https://example.com/a")
    assert response.content == b"safe"
    assert requests[0].url.host == "93.184.216.34"
    assert requests[0].headers["host"] == "example.com"
    assert requests[0].extensions["sni_hostname"] == "example.com"


@pytest.mark.asyncio
async def test_fetch_decodes_compression_once(monkeypatch):
    import gzip
    import httpx
    async def public_host(url):
        return "93.184.216.34"
    monkeypatch.setattr(fetcher, "_check_public_host", public_host)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=gzip.compress(b"decoded")))
    client_type = httpx.AsyncClient
    monkeypatch.setattr(fetcher.httpx, "AsyncClient", lambda **kwargs: client_type(transport=transport, **kwargs))
    assert (await fetcher.fetch_response("https://example.com")).content == b"decoded"
