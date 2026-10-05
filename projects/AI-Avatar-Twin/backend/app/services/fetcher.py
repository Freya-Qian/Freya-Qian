"""URL 抓取与正文清洗（M1 轻量实现，httpx + BeautifulSoup；M2 评估 Crawl4AI）。"""
from __future__ import annotations

import re
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


def validate_url(url: str) -> str:
    """校验并规范化 URL，只允许 http/https，拒绝内网与本地地址。"""
    u = url.strip()
    if not re.match(r"^https?://", u, re.IGNORECASE):
        raise LLMError("INVALID_URL", "只支持 http/https 链接")
    parsed = urlparse(u)
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.endswith(".local"):
        raise LLMError("INVALID_URL", "不支持访问本地或内网地址")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise LLMError("INVALID_URL", "不支持访问本地或内网地址")
    if parsed.username is not None or parsed.password is not None:
        raise LLMError("INVALID_URL", "链接不能包含登录凭据")
    if not host:
        raise LLMError("INVALID_URL", "链接缺少有效主机名")
    return u


def _clean_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


async def _check_public_host(url: str) -> str:
    parsed = urlparse(validate_url(url))
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except (OSError, ValueError):
        raise LLMError("FETCH_ERROR", "无法解析网页地址") from None
    if not addresses or any(not ipaddress.ip_address(info[4][0]).is_global for info in addresses):
        raise LLMError("INVALID_URL", "不支持访问本地或内网地址")
    return addresses[0][4][0]


async def fetch_response(url: str) -> httpx.Response:
    """网页与 RSS 共用抓取；校验解析地址和每一步重定向，限制响应体大小。"""
    url = validate_url(url)
    try:
        for _ in range(6):
            # A fresh connection per hop keeps TLS verification bound to this hop's hostname.
            async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT, follow_redirects=False, trust_env=False) as client:
                address = await _check_public_host(url)
                target = httpx.URL(url)
                # Connect to the checked IP so a second DNS lookup cannot reach a private address.
                # Keep the original Host and TLS server name for virtual hosts and certificate validation.
                pinned_target = target.copy_with(host=address)
                host_header = target.netloc.decode("ascii")
                async with client.stream(
                    "GET", pinned_target,
                    headers={"User-Agent": "Mozilla/5.0 (AvatarTwin/1.0)", "Host": host_header},
                    extensions={"sni_hostname": target.host},
                ) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("location")
                        if not location:
                            raise LLMError("FETCH_ERROR", "网页重定向缺少目标地址")
                        url = validate_url(urljoin(url, location))
                        continue
                    chunks = []
                    size = 0
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > 5 * 1024 * 1024:
                            raise LLMError("FETCH_ERROR", "网页内容过大")
                        chunks.append(chunk)
                    headers = {k: v for k, v in resp.headers.items() if k.lower() not in ("content-encoding", "content-length")}
                    return httpx.Response(resp.status_code, headers=headers, content=b"".join(chunks))
        raise LLMError("FETCH_ERROR", "网页重定向次数过多")
    except httpx.TimeoutException:
        raise LLMError("FETCH_TIMEOUT", "网页抓取超时，请稍后重试") from None
    except httpx.HTTPError:
        raise LLMError("FETCH_ERROR", "网页抓取失败，请检查链接或稍后重试") from None


async def fetch_url(url: str) -> dict:
    """抓取网页并清洗正文。返回 {title, source_name, content_text}。"""
    resp = await fetch_response(url)
    if resp.status_code != 200:
        raise LLMError("FETCH_ERROR", f"网页返回 HTTP {resp.status_code}")

    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype.lower() and "xml" not in ctype.lower():
        raise LLMError("FETCH_ERROR", "该链接不是网页内容")

    soup = BeautifulSoup(resp.text, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else "") or ""
    text = _clean_text(soup)
    text = text[:MAX_CONTENT_CHARS]
    if len(text) < MIN_CONTENT_CHARS:
        raise LLMError("CONTENT_TOO_SHORT", "网页正文过短，可能需登录或为动态页面")

    source_name = urlparse(url).hostname or url

    return {"title": title[:500], "source_name": source_name, "content_text": text}
