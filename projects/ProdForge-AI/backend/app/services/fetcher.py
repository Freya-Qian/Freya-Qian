"""URL 抓取与正文清洗（轻量实现，httpx + BeautifulSoup）。"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.llm import LLMError

MAX_CONTENT_CHARS = 6000
MIN_CONTENT_CHARS = 80
_FETCH_TIMEOUT = 30.0
_MAX_REDIRECTS = 5
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def _public_ip(value: str) -> str:
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address):
        # Refuse scoped and transition addresses, including embedded IPv4 routes.
        if (address.scope_id or address.ipv4_mapped or address.sixtofour or address.teredo
                or address in ipaddress.ip_network("64:ff9b::/96")
                or address in ipaddress.ip_network("64:ff9b:1::/48")):
            raise LLMError("INVALID_URL", "不支持访问本地或内网地址")
    if not address.is_global or address.is_multicast:
        raise LLMError("INVALID_URL", "不支持访问本地或内网地址")
    return str(address)


def validate_url(url: str) -> str:
    """校验 URL：只允许 http/https，拒绝本地/内网地址。"""
    u = (url or "").strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in u) or "\\" in u:
        raise LLMError("INVALID_URL", "链接格式不合法")
    try:
        parsed = httpx.URL(u)
        host = parsed.raw_host.decode("ascii").lower().rstrip(".")
        if parsed.scheme not in ("http", "https"):
            raise LLMError("INVALID_URL", "只支持 http/https 链接")
        if (parsed.userinfo or not host or "%" in host
                or (parsed.port is not None and not 1 <= parsed.port <= 65535)):
            raise LLMError("INVALID_URL", "链接缺少有效主机名或包含用户凭据")
    except (httpx.InvalidURL, ValueError) as exc:
        raise LLMError("INVALID_URL", "链接格式不合法") from exc
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise LLMError("INVALID_URL", "不支持访问本地或内网地址")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass  # DNS validation is asynchronous and happens immediately before fetching.
    else:
        _public_ip(host)
    return u


async def _resolve_virtual_dns(host: str) -> str:
    """Recover public DNS from a local fake-IP resolver, without trusting its IPs."""
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False, trust_env=False) as client:
        response = await client.get(
            "https://1.1.1.1/dns-query",
            params={"name": host, "type": "A"},
            headers={"Host": "cloudflare-dns.com", "Accept": "application/dns-json"},
            extensions={"sni_hostname": "cloudflare-dns.com"},
        )
        response.raise_for_status()
        result = response.json()
    if isinstance(result, dict) and result.get("Status") == 3:
        raise LLMError("FETCH_ERROR", "官网域名不存在，推荐链接可能有误，请更换抓取链接")
    if not isinstance(result, dict) or result.get("Status") != 0:
        raise LLMError("FETCH_ERROR", "公共域名解析失败，请检查网络后重试")
    records = result.get("Answer", [])
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise LLMError("FETCH_ERROR", "公共域名解析返回异常，请稍后重试")
    if any(not isinstance(item.get("data"), str) for item in records if item.get("type") in (1, 28)):
        raise LLMError("FETCH_ERROR", "公共域名解析返回异常，请稍后重试")
    addresses = [_public_ip(item["data"]) for item in records
                 if item.get("type") in (1, 28)]
    if not addresses:
        raise LLMError("FETCH_ERROR", "未找到可访问的公网地址，请换用官网页面链接")
    return addresses[0]


async def _resolve_public(host: str, port: int) -> str:
    try:
        return _public_ip(host)
    except ValueError:
        pass
    answers = await asyncio.get_running_loop().getaddrinfo(
        host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM,
    )
    if not answers:
        raise LLMError("FETCH_ERROR", "网页域名解析失败")
    # TUN proxies may return benchmarking addresses instead of the public DNS answer.
    # Only this range gets a trusted DNS fallback; private/mixed answers still fail.
    virtual_range = ipaddress.ip_network("198.18.0.0/15")
    if all(ipaddress.ip_address(answer[4][0]) in virtual_range for answer in answers):
        return await _resolve_virtual_dns(host)
    # Reject mixed public/private DNS answers rather than selecting a safe subset.
    addresses = [_public_ip(answer[4][0]) for answer in answers]
    return addresses[0]


async def _fetch_public(url: str) -> httpx.Response:
    for hop in range(_MAX_REDIRECTS + 1):
        current = httpx.URL(validate_url(url))
        host = current.raw_host.decode("ascii")
        address = await _resolve_public(host, current.port or (443 if current.scheme == "https" else 80))
        pinned = current.copy_with(host=address)
        # A fresh transport per hop avoids sharing TLS connections across hostnames
        # that resolve to the same IP. Keep certificate verification and SNI on host.
        async with httpx.AsyncClient(
            timeout=_FETCH_TIMEOUT, follow_redirects=False, trust_env=False,
        ) as client:
            resp = await client.get(
                pinned,
                headers={"User-Agent": "Mozilla/5.0 (ProductFactory/1.0)",
                         "Host": current.netloc.decode("ascii")},
                extensions={"sni_hostname": host},
            )
        if resp.status_code not in _REDIRECT_STATUSES:
            return resp
        location = resp.headers.get("location")
        if not location or hop == _MAX_REDIRECTS:
            raise LLMError("FETCH_ERROR", "网页重定向无效或次数过多")
        # Resolve relative locations against the logical URL, never the pinned IP.
        url = urljoin(str(current), location)
    raise LLMError("FETCH_ERROR", "网页重定向次数过多")


def _clean_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


async def fetch_url(url: str) -> dict:
    """抓取网页并清洗正文。返回 {title, source_name, content_text}。"""
    url = validate_url(url)
    try:
        resp = await asyncio.wait_for(_fetch_public(url), timeout=_FETCH_TIMEOUT)
    except (httpx.TimeoutException, asyncio.TimeoutError):
        raise LLMError("FETCH_TIMEOUT", "网页抓取超时，请稍后重试（若为动态页面/反爬站点，可换链接或手动粘贴正文）")
    except (httpx.HTTPError, OSError):
        raise LLMError("FETCH_ERROR", "网页抓取失败，请检查链接或稍后重试")
    except (httpx.InvalidURL, ValueError):
        raise LLMError("INVALID_URL", "链接格式不合法")

    if resp.status_code != 200:
        raise LLMError("FETCH_ERROR", f"网页返回 HTTP {resp.status_code}")

    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype.lower() and "xml" not in ctype.lower():
        raise LLMError("FETCH_ERROR", "该链接不是网页内容")

    soup = BeautifulSoup(resp.text, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else "") or ""
    text = _clean_text(soup)[:MAX_CONTENT_CHARS]
    if len(text) < MIN_CONTENT_CHARS:
        raise LLMError("CONTENT_TOO_SHORT", "网页正文过短，可能需登录或为动态页面")

    return {
        "title": title[:500],
        "source_name": urlparse(url).hostname or url,
        "content_text": text,
    }
