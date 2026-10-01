"""PRD 生成与证据引用审计（M3 核心服务）。

审计三件套（PRD 4.4）：① evidence ref_key 存在性校验；② 只保留真实存在的引用；
③ 结论型章节无证据 → 标"待确认"（无证据结论清单）。
"""
from __future__ import annotations

import json

from app.core.llm import LLMClient, LLMError
from app.services.parser import extract_json
from app.services.prompts import EVIDENCE_REQUIRED_CHAPTERS, GOAL_TYPE_HINT, PRD_CHAPTERS, PRD_SYSTEM


def _normalize_sections(raw: list) -> list[dict]:
    """把模型输出的章节规整为固定 11 章（按序），缺章补空并标"待确认"。"""
    by_title: dict[str, dict] = {}
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        by_title[title] = {
            "title": title,
            "content": str(item.get("content", "")).strip(),
            "evidence_refs": [r for r in (item.get("evidence_refs") or []) if isinstance(r, str)],
            "status": "ok",
        }
    result = []
    for title in PRD_CHAPTERS:
        if title in by_title:
            result.append(by_title[title])
        else:
            result.append({"title": title, "content": "（未生成，待补充）", "evidence_refs": [], "status": "待确认"})
    return result


def audit_sections(sections: list[dict], valid_ref_keys: set) -> tuple[list[dict], list[str]]:
    """证据引用审计：过滤不存在的 ref_key；结论型章节无证据 → 待确认。返回 (sections, 无证据结论清单)。"""
    unverified: list[str] = []
    for s in sections:
        refs = [r for r in s.get("evidence_refs", []) if r in valid_ref_keys]
        s["evidence_refs"] = refs
        if s.get("title") in EVIDENCE_REQUIRED_CHAPTERS and not refs:
            s["status"] = "待确认"
            unverified.append(s["title"])
        else:
            s["status"] = "ok"
    return sections, unverified


async def generate_prd(client: LLMClient, brief: dict, positioning: dict,
                       evidences: list[dict], goal_type: str = "real") -> dict:
    """生成带证据引用的 PRD + 执行证据引用审计。"""
    valid_ref_keys = {e["ref_key"] for e in evidences}
    ev_text = "\n".join(
        f"- {e['ref_key']}（{e['evidence_type']}）：{e['structured_claim']} → 启发：{e['implication']}"
        for e in evidences
    )
    user = (
        "项目目标类型：" + GOAL_TYPE_HINT.get(goal_type, "") + "\n\n"
        "需求摘要：\n" + json.dumps(brief, ensure_ascii=False, indent=1) + "\n\n"
        "产品定位与差异点：\n" + json.dumps({
            "one_liner": positioning.get("one_liner", ""),
            "target_users": positioning.get("target_users", ""),
            "value_proposition": positioning.get("value_proposition", ""),
            "differentiators": positioning.get("differentiators", []),
            "non_goals": positioning.get("non_goals", ""),
        }, ensure_ascii=False, indent=1) + "\n\n"
        "竞品证据卡：\n" + ev_text + "\n\n"
        "请生成完整 PRD。"
    )
    text = await client.complete(PRD_SYSTEM, user, max_tokens=8000, temperature=0.5)
    try:
        data = extract_json(text)
    except LLMError as first_err:
        retry_user = (
            user + "\n\n"
            f"你上一次的输出不是合法 JSON（错误：{first_err.message}）。"
            "请严格只输出一个 JSON 对象，不要任何解释或代码块标记。"
        )
        text = await client.complete(PRD_SYSTEM, retry_user, max_tokens=8000, temperature=0.4)
        data = extract_json(text)

    sections = _normalize_sections(data.get("sections"))
    sections, unverified = audit_sections(sections, valid_ref_keys)
    evidence_refs = [r for r in (data.get("evidence_refs") or []) if r in valid_ref_keys]
    return {"sections": sections, "evidence_refs": evidence_refs, "unverified": unverified}
