"""M1 编排：摘要 / 选题 / 脚本生成 + 版本管理。模型输出走宽容解析 + Pydantic 强校验。"""
from __future__ import annotations

import re
import uuid
from typing import AsyncIterator

from pydantic import BaseModel, field_validator

from app.config import settings
from app.core.llm import LLMClient, LLMError
from app.services import prompts
from app.services.parser import parse_json

# ---------- 模型输出校验结构 ----------


def _clamp(v, lo=0, hi=100):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return 0


_FABRICATION_PATTERNS = [
    (r"我们实测|我们测试|我们验证|我们复现|我们跑过", "疑似第一人称实测表述（系统无实测能力）"),
    (r"我实测|我测试|我验证|我复现", "疑似第一人称实测表述（系统无实测能力）"),
]


def _detect_fabrication(content: str, risk_flags: list[str]) -> list[str]:
    """兜底扫描脚本正文，命中禁用表述则追加风险标注，防止模型自报'无'蒙混。"""
    flags = list(risk_flags or [])
    for pattern, msg in _FABRICATION_PATTERNS:
        if re.search(pattern, content) and msg not in flags:
            flags.append(msg)
    return flags


def _detect_single_source(source_urls: list[str], risk_flags: list[str]) -> list[str]:
    """来源不足 2 个时自动补"单一来源"标签，防止模型漏标（PRD 7.4）。"""
    flags = list(risk_flags or [])
    sources = [u for u in (source_urls or []) if u and str(u).strip()]
    if len(sources) < 2 and "单一来源" not in flags:
        flags.append("单一来源")
    return flags


def _truncate_content(content: str, duration_seconds: int) -> str:
    """按时长截断脚本正文（约 5 字/秒），在句末截断，避免 TTS 配音超长。"""
    max_chars = duration_seconds * 5
    if len(content) <= max_chars:
        return content
    cut = content[:max_chars]
    for i in range(len(cut) - 1, -1, -1):
        if cut[i] in "。！？!?；;":
            return cut[: i + 1]
    return cut


class SummaryResult(BaseModel):
    title: str = ""
    summary: str = ""
    keywords: list[str] = []
    is_official: bool = False
    credibility_score: int = 0
    video_potential_score: int = 0

    @field_validator("credibility_score", "video_potential_score", mode="before")
    @classmethod
    def _score(cls, v):
        return _clamp(v)

    @field_validator("keywords", mode="before")
    @classmethod
    def _keywords(cls, v):
        return [str(x) for x in v] if isinstance(v, list) else []


class TopicResult(BaseModel):
    title: str = ""
    angle: str = ""
    one_liner: str = ""
    key_facts: list[str] = []
    source_urls: list[str] = []
    score: int = 0
    score_breakdown: dict = {}
    risk_level: str = "low"
    risk_flags: list[str] = []

    @field_validator("score", mode="before")
    @classmethod
    def _score(cls, v):
        return _clamp(v)

    @field_validator("key_facts", "source_urls", "risk_flags", mode="before")
    @classmethod
    def _str_list(cls, v):
        return [str(x) for x in v] if isinstance(v, list) else []

    @field_validator("risk_level", mode="before")
    @classmethod
    def _risk(cls, v):
        return v if v in ("low", "medium", "high") else "low"


class TopicsResult(BaseModel):
    topics: list[TopicResult] = []


class ScriptResult(BaseModel):
    content: str = ""
    fact_claims: list[str] = []
    risk_flags: list[str] = []
    source_urls: list[str] = []

    @field_validator("fact_claims", "risk_flags", "source_urls", mode="before")
    @classmethod
    def _str_list(cls, v):
        return [str(x) for x in v] if isinstance(v, list) else []


# ---------- 工具 ----------


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _client() -> LLMClient:
    return LLMClient()


async def _generate_json(client: LLMClient, system: str, user: str,
                         max_tokens: int = 2000, temperature: float = 0.6) -> dict:
    """模型输出 JSON：宽容解析失败则追加纠正提示，有限重试（最多 2 次）。"""
    last_err: LLMError | None = None
    attempt_user = user
    for _ in range(3):  # 解析类失败最多 3 次，网络重试由 complete 内部处理
        text = await client.complete(system, attempt_user, max_tokens=max_tokens, temperature=temperature)
        try:
            return parse_json(text)
        except LLMError as e:
            last_err = e
            attempt_user = user + "\n\n注意：上次输出不是合法 JSON。请严格只输出一个 JSON 对象，不要代码块、不要解释。"
    raise last_err if last_err else LLMError("PARSE_ERROR", "模型多次输出不合规 JSON")


# ---------- 摘要 ----------


async def summarize_source(client: LLMClient, source) -> None:
    user = prompts.SUMMARY_USER.format(
        title=source.title or "（无标题）",
        url=source.original_url,
        content=source.content_text,
    )
    data = await _generate_json(client, prompts.SUMMARY_SYSTEM, user)
    result = SummaryResult.model_validate(data)
    source.title = result.title or source.title
    source.summary = result.summary
    source.keywords = result.keywords
    source.is_official = 1 if result.is_official else 0
    source.credibility_score = result.credibility_score
    source.video_potential_score = result.video_potential_score
    source.status = "summarized"


# ---------- 选题 ----------


async def generate_topics(client: LLMClient, source) -> list:
    user = prompts.TOPICS_USER.format(
        title=source.title,
        summary=source.summary,
        keywords="、".join(source.keywords or []),
        url=source.original_url,
    )
    data = await _generate_json(client, prompts.TOPICS_SYSTEM, user, max_tokens=2500)
    result = TopicsResult.model_validate(data)
    if not result.topics:
        raise LLMError("PARSE_ERROR", "模型未生成任何选题")
    return result.topics


# ---------- 脚本（SSE 流式） ----------


async def generate_script_stream(client: LLMClient, topic, source, profile=None) -> AsyncIterator[dict]:
    """生成脚本并流式产出事件。事件：chunk → done/error。profile 为 AvatarProfile 或 None（用默认人设）。"""
    sources_text = "\n".join(topic.source_urls or [source.original_url]) or source.original_url
    p = profile
    user = prompts.SCRIPT_USER.format(
        duration=settings.script_duration,
        char_range=f"{settings.script_duration * 4}-{settings.script_duration * 5}",
        max_chars=settings.script_duration * 6,
        style="、".join(p.style_tags) if p and p.style_tags else "专业",
        language=(p.language if p and p.language else "zh"),
        catchphrases="、".join(p.catchphrases) if p and p.catchphrases else "无",
        banned_phrases="、".join(p.banned_phrases) if p and p.banned_phrases else "无",
        topic_direction="、".join(p.topic_preferences) if p and p.topic_preferences else "AI 行业综合",
        topic_title=topic.title,
        angle=topic.angle,
        one_liner=topic.one_liner,
        key_facts="；".join(topic.key_facts or []),
        sources=sources_text,
    )

    accumulated = ""
    try:
        async for delta in client.stream(prompts.SCRIPT_SYSTEM, user, max_tokens=2500, temperature=0.7):
            accumulated += delta
            yield {"type": "chunk", "delta": delta}
    except LLMError as e:
        yield {"type": "error", "error": {"code": e.code, "message": e.message}}
        return

    try:
        data = parse_json(accumulated)
    except LLMError as e:
        yield {"type": "error", "error": {"code": e.code, "message": e.message}}
        return

    try:
        result = ScriptResult.model_validate(data)
    except Exception:
        yield {"type": "error", "error": {"code": "PARSE_ERROR", "message": "脚本结构校验失败"}}
        return

    # 兜底：扫描正文是否有编造表述，命中则追加风险标注
    result.risk_flags = _detect_fabrication(result.content, result.risk_flags)
    # 兜底：来源不足 2 个时自动标"单一来源"，防止模型漏标
    result.risk_flags = _detect_single_source(result.source_urls, result.risk_flags)
    # 硬截断：按目标时长控制脚本长度，避免模型超字数导致配音超长
    result.content = _truncate_content(result.content, settings.script_duration)

    yield {"type": "done", "script": result.model_dump()}
