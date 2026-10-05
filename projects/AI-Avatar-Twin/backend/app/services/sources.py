"""信息源抓取：URL / 手动 / RSS，同一链接去重（复用 fetcher）。"""
from __future__ import annotations

import asyncio
import hashlib

import feedparser

from app.core.llm import LLMError
from app.models import SourceItem
from app.services import engine, fetcher

_RSS_TIMEOUT = 20.0


def _exists(db, user_id: str, original_url: str) -> bool:
    return db.query(SourceItem).filter(
        SourceItem.user_id == user_id, SourceItem.original_url == original_url
    ).first() is not None


def _new_item(source, user_id: str, title: str, url: str, content: str, published_at: str | None = None) -> SourceItem:
    return SourceItem(
        id=engine._gen_id("itm"),
        user_id=user_id,
        source_id=source.id,
        source_type=source.source_type,
        source_name=source.name or source.url,
        original_url=url,
        title=title[:500],
        content_text=content,
        published_at=published_at,
        status="fetched",
    )


async def _fetch_url(db, source, user_id: str) -> list[SourceItem]:
    fetched = await fetcher.fetch_url(source.url)
    if _exists(db, user_id, source.url):
        return []
    item = _new_item(source, user_id, fetched["title"], source.url, fetched["content_text"])
    db.add(item)
    return [item]


async def _fetch_rss(db, source, user_id: str) -> list[SourceItem]:
    try:
        response = await asyncio.wait_for(fetcher.fetch_response(source.url), timeout=_RSS_TIMEOUT)
        if response.status_code != 200:
            raise LLMError("FETCH_ERROR", f"RSS 返回 HTTP {response.status_code}")
        parsed = await asyncio.to_thread(feedparser.parse, response.content)
    except asyncio.TimeoutError:
        raise LLMError("FETCH_TIMEOUT", "RSS 抓取超时，请稍后重试")
    if parsed.bozo and not parsed.entries:
        raise LLMError("FETCH_ERROR", "RSS 解析失败，请检查订阅地址")
    created = []
    for entry in parsed.entries[:20]:
        link = getattr(entry, "link", "") or ""
        if not link or _exists(db, user_id, link):
            continue
        title = getattr(entry, "title", "") or ""
        summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
        published = getattr(entry, "published", None) or getattr(entry, "updated", None) or None
        item = _new_item(source, user_id, title, link, summary, published)
        db.add(item)
        created.append(item)
    return created


def _fetch_manual(db, source, user_id: str) -> list[SourceItem]:
    if not source.content.strip():
        raise LLMError("INVALID_INPUT", "手动信息源缺少正文内容")
    digest = hashlib.md5(source.content.encode("utf-8")).hexdigest()[:16]
    if _exists(db, user_id, f"manual://{digest}"):
        return []
    item = _new_item(source, user_id, source.name or "手动输入", f"manual://{digest}", source.content)
    db.add(item)
    return [item]


async def fetch_source_items(db, source, user_id: str) -> list[SourceItem]:
    """按信息源类型抓取，返回新创建的 SourceItem 列表（去重后可能为空）。"""
    if source.status != "active":
        raise LLMError("INVALID_INPUT", "信息源已禁用，请先启用")
    if source.source_type == "url":
        return await _fetch_url(db, source, user_id)
    if source.source_type == "rss":
        return await _fetch_rss(db, source, user_id)
    if source.source_type == "manual":
        return _fetch_manual(db, source, user_id)
    raise LLMError("INVALID_INPUT", "不支持的信息源类型")
