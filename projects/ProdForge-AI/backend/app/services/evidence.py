"""竞品证据卡：贴网址自动抓取 + 结构化生成（MVP 方案 A）。"""
from __future__ import annotations

from app.core.llm import LLMClient, LLMError
from app.services.parser import extract_json
from app.services.prompts import EVIDENCE_FETCH_SYSTEM, EVIDENCE_TYPES


def normalize(data: dict) -> dict:
    et = str(data.get("evidence_type", "")).strip()
    if et not in EVIDENCE_TYPES:
        et = "功能"
    return {
        "evidence_type": et,
        "structured_claim": str(data.get("structured_claim", "")).strip(),
        "implication": str(data.get("implication", "")).strip(),
        "raw_excerpt": str(data.get("raw_excerpt", "")).strip(),
        "confidence": "合理推断",  # 自动抓取，固定"合理推断"，未经人工核实
    }


async def generate_evidence(client: LLMClient, competitor_name: str,
                            project_idea: str, fetched: dict) -> dict:
    """根据抓取到的网页内容生成结构化证据卡。"""
    user = (
        f"竞品名称：{competitor_name}\n"
        f"网页标题：{fetched['title']}\n"
        f"网页正文：\n{fetched['content_text']}\n\n"
        f"用户项目想法：{project_idea}\n\n"
        "请生成竞品证据卡。"
    )
    text = await client.complete(EVIDENCE_FETCH_SYSTEM, user, max_tokens=1200, temperature=0.4)
    try:
        data = extract_json(text)
    except LLMError:
        # 解析失败时确定性兜底：用网页标题/正文前段，标"合理推断"，由用户后续编辑
        return {
            "evidence_type": "功能",
            "structured_claim": (fetched.get("title") or "（抓取内容无法解析，请手动补充结论）")[:200],
            "implication": "",
            "raw_excerpt": (fetched.get("content_text") or "")[:200],
            "confidence": "合理推断",
        }
    return normalize(data)
