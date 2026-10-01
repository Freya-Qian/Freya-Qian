"""产品定位与差异点生成（M2 核心服务）：基于需求摘要 + 竞品证据，证据引用校验。"""
from __future__ import annotations

import json

from app.core.llm import LLMClient, LLMError
from app.services.parser import extract_json
from app.services.prompts import POSITIONING_SYSTEM


def _clean_differentiators(raw: list, valid_ref_keys: set) -> list[dict]:
    result = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        point = str(item.get("point", "")).strip()
        if not point:
            continue
        refs = [r for r in (item.get("evidence_refs") or []) if r in valid_ref_keys]
        if not refs:
            # 无证据支撑的差异点显式标注“待补证”（PRD 10.4 不编造）
            point = point + "（待补证：无证据引用）"
        result.append({"point": point, "evidence_refs": refs})
    return result


def _clean_comparison(raw: list) -> list[dict]:
    """规整多竞品对比表：competitors 为 {竞品名: 事实}，our_product 为用户产品。"""
    result = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        dim = str(item.get("dimension", "")).strip()
        if not dim:
            continue
        competitors: dict[str, str] = {}
        comps = item.get("competitors")
        if isinstance(comps, dict):
            for k, v in comps.items():
                k = str(k).strip()
                if k:
                    competitors[k] = str(v).strip()
        result.append({
            "dimension": dim,
            "competitors": competitors,
            "our_product": str(item.get("our_product", "")).strip(),
        })
    return result


def _evidence_text(evidences: list[dict]) -> str:
    lines = []
    for e in evidences:
        lines.append(
            f"- ref_key={e['ref_key']}（{e['evidence_type']}）：{e['structured_claim']} → 启发：{e['implication']}"
        )
    return "\n".join(lines)


def normalize(data: dict, valid_ref_keys: set) -> dict:
    """规整模型输出 + 证据引用校验（只保留真实存在的 ref_key，不编造）。"""
    return {
        "one_liner": str(data.get("one_liner", "")).strip(),
        "target_users": str(data.get("target_users", "")).strip(),
        "value_proposition": str(data.get("value_proposition", "")).strip(),
        "non_goals": str(data.get("non_goals", "")).strip(),
        "differentiators": _clean_differentiators(data.get("differentiators"), valid_ref_keys),
        "comparison": _clean_comparison(data.get("comparison")),
        "evidence_refs": [r for r in (data.get("evidence_refs") or []) if r in valid_ref_keys],
    }


async def generate_positioning(client: LLMClient, brief: dict, evidences: list[dict]) -> dict:
    """生成定位与差异点。JSON 不可解析时纠错重试一次。"""
    valid_ref_keys = {e["ref_key"] for e in evidences}
    user = (
        "需求摘要：\n" + json.dumps(brief, ensure_ascii=False, indent=1) + "\n\n"
        "竞品证据卡：\n" + _evidence_text(evidences) + "\n\n"
        "请生成产品定位与差异点。"
    )
    text = await client.complete(POSITIONING_SYSTEM, user, max_tokens=2500, temperature=0.5)
    try:
        data = extract_json(text)
    except LLMError as first_err:
        retry_user = (
            user + "\n\n"
            f"你上一次的输出不是合法 JSON（错误：{first_err.message}）。"
            "请严格只输出一个 JSON 对象，不要任何解释或代码块标记。"
        )
        text = await client.complete(POSITIONING_SYSTEM, retry_user, max_tokens=2500, temperature=0.4)
        data = extract_json(text)
    return normalize(data, valid_ref_keys)
