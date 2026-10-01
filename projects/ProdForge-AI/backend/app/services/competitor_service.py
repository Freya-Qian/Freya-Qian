"""竞品与证据卡：source_url 校验、ref_key 生成、竞品推荐（竞品由用户自选，不硬编码任何竞品）。"""
from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.llm import LLMError
from app.models import Competitor, CompetitorEvidence
from app.services.parser import extract_json
from app.services.prompts import COMPETITOR_RECOMMEND_SYSTEM

# MVP 竞品数量上限（产品经理决策：≤3 个用户自己项目的竞品）
MAX_COMPETITORS = 3


def validate_source_url(url: str) -> str:
    """source_url 必填 + 格式校验（PRD 10.3 P0：http/https）。"""
    url = (url or "").strip()
    if not url:
        raise LLMError("INVALID_INPUT", "source_url 必填")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise LLMError("INVALID_INPUT", "source_url 必须是以 http/https 开头的合法链接")
    return url


def next_ref_key(db: Session, competitor_id: str) -> str:
    """Allocate the next project-wide key, including keys still cited by content."""
    comp = db.get(Competitor, competitor_id)
    if comp is None:
        raise LLMError("NOT_FOUND", "竞品不存在")
    keys = db.query(CompetitorEvidence.ref_key).filter(
        CompetitorEvidence.project_id == comp.project_id,
    ).all()
    highest = max((int(key[1:]) for (key,) in keys
                   if key.startswith("E") and key[1:].isdigit()), default=0)
    # Keep keys referenced by historical content reserved even if evidence was deleted.
    from app.models import DecisionLog, DevTask, Positioning, ProductDoc
    import json
    for model, fields in (
        (Positioning, ("evidence_refs", "differentiators")),
        (ProductDoc, ("evidence_refs", "sections")),
        (DevTask, ("source_refs",)),
        (DecisionLog, ("evidence_refs",)),
    ):
        for row in db.query(model).filter(model.project_id == comp.project_id).all():
            for field in fields:
                try:
                    values = json.loads(getattr(row, field) or "[]")
                except (TypeError, ValueError):
                    continue
                if not isinstance(values, list):
                    continue
                refs = values if field not in ("sections", "differentiators") else [ref for item in values if isinstance(item, dict) for ref in (item.get("evidence_refs") or [])]
                highest = max([highest, *(int(ref[1:]) for ref in refs
                                          if isinstance(ref, str) and ref.startswith("E") and ref[1:].isdigit())])
    return f"E{highest + 1}"


async def recommend_competitors(client, idea: str, goal_type: str = "real") -> list[dict]:
    """根据项目想法推荐 2-3 个真实竞品（名称 + 官网链接 + 一句话定位）。

    链接校验：模型输出不可靠，只保留 http/https 开头的链接，其余置空（宁缺毋滥）。
    """
    user = f"项目想法：{idea}\n目标类型：{goal_type}\n请推荐竞品。"
    text = await client.complete(COMPETITOR_RECOMMEND_SYSTEM, user, max_tokens=1000, temperature=0.5)
    try:
        data = extract_json(text)
    except LLMError as first_err:
        retry_user = (
            user + "\n\n"
            f"你上一次的输出不是合法 JSON（错误：{first_err.message}）。"
            "请严格只输出一个 JSON 对象，不要任何解释或代码块标记。"
        )
        text = await client.complete(COMPETITOR_RECOMMEND_SYSTEM, retry_user, max_tokens=1000, temperature=0.4)
        data = extract_json(text)

    result = []
    for c in data.get("competitors", []) if isinstance(data, dict) else []:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name", "")).strip()
        if not name:
            continue
        url = str(c.get("url", "")).strip()
        if url and not url.startswith(("http://", "https://")):
            url = ""
        result.append({
            "name": name,
            "url": url,
            "positioning": str(c.get("positioning", "")).strip(),
        })
        if len(result) >= 3:
            break
    return result
