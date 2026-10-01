"""SSRF regression tests; DNS and HTTP are mocked, never sent externally."""
import asyncio
import socket
import ssl

import httpx
import pytest
from httpcore._backends.anyio import AnyIOBackend

from app.core.llm import LLMError
from app.services import fetcher


HTML = "<html><title>Public page</title><nav>ignore me</nav><p>" + "Readable content. " * 20 + "</p></html>"
PUBLIC = "93.184.216.34"


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected network access")

    monkeypatch.setattr(AnyIOBackend, "connect_tcp", forbidden)


def mock_fetch(monkeypatch, dns, responses):
    requests, resolutions = [], []

    async def resolve(host, port, **kwargs):
        resolutions.append((host, port))
        answers = dns[host]
        if isinstance(answers, Exception):
            raise answers
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET,
                 socket.SOCK_STREAM, 6, "", (ip, port)) for ip in answers]

    def respond(request):
        requests.append(request)
        response = responses[len(requests) - 1]
        if isinstance(response, Exception):
            raise response
        return response

    original_client = httpx.AsyncClient

    def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return original_client(**kwargs, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    monkeypatch.setattr(fetcher.httpx, "AsyncClient", client)
    return requests, resolutions


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com/a", "https:///missing",
    "http://localhost", "http://localhost.", "http://a.localhost", "http://a.local",
    "http://127.0.0.2", "http://0.0.0.0", "http://10.1.2.3", "http://172.16.0.1",
    "http://192.168.1.1", "http://169.254.169.254", "http://100.64.0.1",
    "http://224.0.0.1", "http://[::1]", "http://[::]", "http://[fc00::1]",
    "http://[fe80::1]", "http://[ff02::1]", "http://[::ffff:127.0.0.1]",
    "http://[64:ff9b::a00:1]", "http://[2002:7f00:1::]", "http://[fe80::1%25eth0]",
    "http://user:password@example.com", "http://example.com:0", "http://example.com:99999",
    "http://[broken", "http://example.com\\@127.0.0.1", "http://example.com/\nfoo",
])
def test_reject_unsafe_url_syntax_and_literals(url):
    with pytest.raises(LLMError) as exc:
        fetcher.validate_url(url)
    assert exc.value.code == "INVALID_URL"


@pytest.mark.asyncio
@pytest.mark.parametrize("host,answers", [
    ("internal.example", ["10.0.0.1"]),
    ("mixed.example", [PUBLIC, "192.168.0.1"]),
    ("mixed.example", [PUBLIC, "::1"]),
    ("2130706433", ["127.0.0.1"]),
    ("127.1", ["127.0.0.1"]),
    ("0x7f000001", ["127.0.0.1"]),
])
async def test_reject_private_dns_and_numeric_aliases(monkeypatch, host, answers):
    requests, _ = mock_fetch(monkeypatch, {host: answers}, [])
    with pytest.raises(LLMError) as exc:
        await fetcher.fetch_url(f"http://{host}/")
    assert exc.value.code == "INVALID_URL"
    assert requests == []


@pytest.mark.asyncio
async def test_pins_ip_preserves_host_tls_and_output_contract(monkeypatch):
    requests, resolutions = mock_fetch(monkeypatch, {"public.example": [PUBLIC]}, [
        httpx.Response(200, headers={"content-type": "text/html"}, text=HTML),
    ])
    result = await fetcher.fetch_url("https://public.example:8443/path?q=1")
    assert set(result) == {"title", "source_name", "content_text"}
    assert result["title"] == "Public page"
    assert result["source_name"] == "public.example"
    assert "ignore me" not in result["content_text"]
    assert resolutions == [("public.example", 8443)]
    assert str(requests[0].url) == f"https://{PUBLIC}:8443/path?q=1"
    assert requests[0].headers["host"] == "public.example:8443"
    assert requests[0].extensions["sni_hostname"] == "public.example"


@pytest.mark.asyncio
@pytest.mark.parametrize("location", [
    "http://169.254.169.254/latest/meta-data", "//127.0.0.1/admin",
    "https://private.example/", "file:///etc/passwd", "http://user:pass@public.example",
])
async def test_redirect_target_checked_before_request(monkeypatch, location):
    requests, _ = mock_fetch(monkeypatch, {"public.example": [PUBLIC], "private.example": ["10.0.0.1"]}, [
        httpx.Response(302, headers={"location": location}),
    ])
    with pytest.raises(LLMError) as exc:
        await fetcher.fetch_url("https://public.example/start")
    assert exc.value.code == "INVALID_URL"
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_relative_redirect_and_cross_host_redirect(monkeypatch):
    requests, resolutions = mock_fetch(monkeypatch, {
        "public.example": [PUBLIC], "next.example": ["2606:4700:4700::1111"],
    }, [
        httpx.Response(301, headers={"location": "../next"}),
        httpx.Response(307, headers={"location": "https://next.example/final"}),
        httpx.Response(200, headers={"content-type": "text/html"}, text=HTML),
    ])
    result = await fetcher.fetch_url("https://public.example/a/start")
    assert result["source_name"] == "public.example"
    assert resolutions == [("public.example", 443), ("public.example", 443), ("next.example", 443)]
    assert requests[1].url.path == "/next"
    assert requests[2].url.host == "2606:4700:4700::1111"
    assert requests[2].headers["host"] == "next.example"
    assert requests[2].extensions["sni_hostname"] == "next.example"


@pytest.mark.asyncio
async def test_rebinding_on_redirect_is_rejected(monkeypatch):
    answers = {"public.example": [PUBLIC]}
    requests, _ = mock_fetch(monkeypatch, answers, [httpx.Response(302, headers={"location": "/next"})])
    original_resolve = fetcher._resolve_public

    async def resolve(host, port):
        result = await original_resolve(host, port)
        answers[host] = ["127.0.0.1"]
        return result

    monkeypatch.setattr(fetcher, "_resolve_public", resolve)
    with pytest.raises(LLMError) as exc:
        await fetcher.fetch_url("https://public.example/")
    assert exc.value.code == "INVALID_URL"
    assert len(requests) == 1
    assert requests[0].url.host == PUBLIC


@pytest.mark.asyncio
async def test_redirect_loop_is_bounded(monkeypatch):
    requests, _ = mock_fetch(monkeypatch, {"public.example": [PUBLIC]}, [
        httpx.Response(302, headers={"location": "/loop"}) for _ in range(fetcher._MAX_REDIRECTS + 1)
    ])
    with pytest.raises(LLMError) as exc:
        await fetcher.fetch_url("https://public.example/")
    assert exc.value.code == "FETCH_ERROR"
    assert len(requests) == fetcher._MAX_REDIRECTS + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("response,code", [
    (httpx.Response(302), "FETCH_ERROR"),
    (httpx.Response(404), "FETCH_ERROR"),
    (httpx.Response(200, headers={"content-type": "application/pdf"}), "FETCH_ERROR"),
    (httpx.Response(200, headers={"content-type": "text/html"}, text="short"), "CONTENT_TOO_SHORT"),
    (httpx.ConnectTimeout("timeout"), "FETCH_TIMEOUT"),
    (httpx.ConnectError("failed"), "FETCH_ERROR"),
])
async def test_existing_error_contract(monkeypatch, response, code):
    mock_fetch(monkeypatch, {"public.example": [PUBLIC]}, [response])
    with pytest.raises(LLMError) as exc:
        await fetcher.fetch_url("https://public.example/")
    assert exc.value.code == code


@pytest.mark.asyncio
@pytest.mark.parametrize("answers,code", [
    ([], "FETCH_ERROR"), (socket.gaierror("not found"), "FETCH_ERROR"),
    (asyncio.TimeoutError(), "FETCH_TIMEOUT"),
])
async def test_dns_errors_are_structured(monkeypatch, answers, code):
    requests, _ = mock_fetch(monkeypatch, {"public.example": answers}, [])
    with pytest.raises(LLMError) as exc:
        await fetcher.fetch_url("https://public.example/")
    assert exc.value.code == code
    assert requests == []


@pytest.mark.asyncio
async def test_real_transport_connects_to_pinned_ip_and_verifies_original_tls_host(monkeypatch):
    connections, tls_hosts, writes = [], [], []

    class Stream:
        async def start_tls(self, ssl_context, server_hostname, timeout):
            assert ssl_context.check_hostname is True
            assert ssl_context.verify_mode == ssl.CERT_REQUIRED
            tls_hosts.append(server_hostname)
            return self

        async def write(self, buffer, timeout=None):
            writes.append(buffer)

        async def read(self, max_bytes, timeout=None):
            body = HTML.encode()
            return (f"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: {len(body)}\r\n\r\n".encode()
                    + body)

        async def aclose(self):
            pass

        def get_extra_info(self, info):
            return None

    async def connect(self, host, port, **kwargs):
        connections.append((host, port))
        return Stream()

    async def resolve(host, port, **kwargs):
        assert host == "public.example"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC, port))]

    monkeypatch.setattr(AnyIOBackend, "connect_tcp", connect)
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    result = await fetcher.fetch_url("https://public.example/")
    assert result["title"] == "Public page"
    assert connections == [(PUBLIC, 443)]
    assert tls_hosts == ["public.example"]
    assert b"Host: public.example\r\n" in b"".join(writes)


def dns_response(addresses):
    return httpx.Response(200, json={
        "Status": 0,
        "Answer": [{"type": 28 if ":" in address else 1, "data": address}
                   for address in addresses],
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("system_answers", [
    ["198.18.0.104"], ["198.18.0.0", "198.19.255.255"],
])
async def test_virtual_dns_fallback_pins_resolver_and_destination(monkeypatch, system_answers):
    requests, resolutions = mock_fetch(monkeypatch, {"webarena.example": system_answers}, [
        dns_response(["185.199.108.153", "185.199.109.153"]),
        httpx.Response(200, headers={"content-type": "text/html"}, text=HTML),
    ])
    result = await fetcher.fetch_url("https://webarena.example:8443/path?q=1")
    assert resolutions == [("webarena.example", 8443)]
    assert len(requests) == 2
    resolver, page = requests
    assert resolver.method == "GET"
    assert str(resolver.url).split("?")[0] == "https://1.1.1.1/dns-query"
    assert dict(resolver.url.params) == {"name": "webarena.example", "type": "A"}
    assert resolver.headers["host"] == "cloudflare-dns.com"
    assert resolver.headers["accept"] == "application/dns-json"
    assert resolver.extensions["sni_hostname"] == "cloudflare-dns.com"
    assert resolver.extensions["timeout"]["connect"] == 10.0
    # mock_fetch also asserts trust_env=False and follow_redirects=False per client.
    assert str(page.url) == "https://185.199.108.153:8443/path?q=1"
    assert page.headers["host"] == "webarena.example:8443"
    assert page.extensions["sni_hostname"] == "webarena.example"
    assert result["source_name"] == "webarena.example"
    assert result["title"] == "Public page"


@pytest.mark.asyncio
@pytest.mark.parametrize("answers", [
    ["10.0.0.1"], ["127.0.0.1"], ["169.254.169.254"], ["::1"],
    ["198.18.0.104", "10.0.0.1"], ["198.18.0.104", PUBLIC],
    [PUBLIC, "198.19.255.255"], ["198.18.0.104", "::1"],
    [PUBLIC, "192.168.0.1"],
])
async def test_virtual_dns_never_falls_back_for_private_or_mixed_answers(monkeypatch, answers):
    requests, resolutions = mock_fetch(monkeypatch, {"target.example": answers}, [])
    with pytest.raises(LLMError) as exc:
        await fetcher.fetch_url("https://target.example/")
    assert exc.value.code == "INVALID_URL"
    assert resolutions == [("target.example", 443)]
    assert requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("host", ["198.18.0.104", "198.19.255.255", "10.0.0.1", "[::1]"])
async def test_virtual_dns_never_falls_back_for_nonpublic_literal(monkeypatch, host):
    requests, resolutions = mock_fetch(monkeypatch, {}, [])
    with pytest.raises(LLMError) as exc:
        await fetcher.fetch_url(f"https://{host}/")
    assert exc.value.code == "INVALID_URL"
    assert requests == resolutions == []


@pytest.mark.asyncio
@pytest.mark.parametrize("literal", [False, True])
async def test_public_destination_does_not_use_virtual_dns_fallback(monkeypatch, literal):
    host = PUBLIC if literal else "public.example"
    requests, resolutions = mock_fetch(monkeypatch, {host: [PUBLIC]}, [
        httpx.Response(200, headers={"content-type": "text/html"}, text=HTML),
    ])
    await fetcher.fetch_url(f"https://{host}/")
    assert len(requests) == 1
    assert requests[0].url.host == PUBLIC
    assert resolutions == ([] if literal else [(host, 443)])


@pytest.mark.asyncio
@pytest.mark.parametrize("addresses", [
    ["10.0.0.1"], ["169.254.169.254"], ["198.18.0.104"], ["::1"],
    [PUBLIC, "10.0.0.1"], [PUBLIC, "::1"], ["10.0.0.1", PUBLIC],
])
async def test_virtual_dns_validates_every_returned_address(monkeypatch, addresses):
    requests, _ = mock_fetch(monkeypatch, {"target.example": ["198.18.0.104"]}, [
        dns_response(addresses),
    ])
    with pytest.raises(LLMError) as exc:
        await fetcher.fetch_url("https://target.example/")
    assert exc.value.code == "INVALID_URL"
    assert len(requests) == 1
    assert requests[0].url.host == "1.1.1.1"


@pytest.mark.asyncio
@pytest.mark.parametrize("response,code", [
    (httpx.Response(503), "FETCH_ERROR"),
    (httpx.Response(302, headers={"location": "http://127.0.0.1/dns-query"}), "FETCH_ERROR"),
    (httpx.ConnectError("resolver unavailable"), "FETCH_ERROR"),
    (httpx.ReadTimeout("resolver timeout"), "FETCH_TIMEOUT"),
    (httpx.Response(200, text="not json"), "INVALID_URL"),
    (httpx.Response(200, json=[]), "FETCH_ERROR"),
    (httpx.Response(200, json={"Status": 3}), "FETCH_ERROR"),
    (httpx.Response(200, json={"Status": 0}), "FETCH_ERROR"),
    (httpx.Response(200, json={"Status": 0, "Answer": []}), "FETCH_ERROR"),
    (httpx.Response(200, json={"Status": 0, "Answer": [{"type": 5, "data": "alias.example"}]}), "FETCH_ERROR"),
    (httpx.Response(200, json={"Status": 0, "Answer": [{"type": 1, "data": "invalid-ip"}]}), "INVALID_URL"),
])
async def test_virtual_dns_failures_stop_before_destination(monkeypatch, response, code):
    requests, _ = mock_fetch(monkeypatch, {"target.example": ["198.18.0.104"]}, [response])
    with pytest.raises(LLMError) as exc:
        await fetcher.fetch_url("https://target.example/")
    assert exc.value.code == code
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [None, {}, [None], ["invalid"], [{"type": 1}],
                                         [{"type": 1, "data": 134744072}]],
                         ids=["null-answer", "object-answer", "null-item", "string-item", "missing-data", "integer-ip"])
async def test_virtual_dns_malformed_schema_must_fail_closed_with_business_error(monkeypatch, answer):
    requests, _ = mock_fetch(monkeypatch, {"target.example": ["198.18.0.104"]}, [
        httpx.Response(200, json={"Status": 0, "Answer": answer}),
        httpx.Response(200, headers={"content-type": "text/html"}, text=HTML),
    ])
    try:
        with pytest.raises(LLMError) as exc:
            await fetcher.fetch_url("https://target.example/")
        assert exc.value.code == "FETCH_ERROR"
    finally:
        assert len(requests) == 1, "Malformed DNS data must not reach the destination"


@pytest.mark.asyncio
async def test_virtual_dns_fallback_still_checks_redirect_destination(monkeypatch):
    requests, _ = mock_fetch(monkeypatch, {
        "target.example": ["198.18.0.104"], "internal.example": ["10.0.0.1"],
    }, [
        dns_response([PUBLIC]),
        httpx.Response(302, headers={"location": "https://internal.example/"}),
    ])
    with pytest.raises(LLMError) as exc:
        await fetcher.fetch_url("https://target.example/")
    assert exc.value.code == "INVALID_URL"
    assert [request.url.host for request in requests] == ["1.1.1.1", PUBLIC]
