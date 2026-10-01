"""需求澄清与需求摘要生成（M1 核心服务）。

模型调用集中在服务层，解析用确定性代码 + 兜底补齐，校验失败抛统一 LLMError。
"""
from __future__ import annotations

from app.core.llm import LLMClient, LLMError
from app.services.parser import extract_json
from app.services.prompts import (
    BRIEF_FIELDS,
    BRIEF_SYSTEM,
    CLARIFY_SYSTEM,
    DEFAULT_QUESTIONS,
    DIMENSIONS,
)


def _normalize_questions(raw: list) -> list[dict]:
    """把模型输出的问题列表规整为 8 个维度各 1 问；缺维度用兜底补齐，重复维度取第一条。"""
    seen: dict[str, dict] = {}
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        dim = str(item.get("dimension", "")).strip()
        q = str(item.get("question", "")).strip()
        if dim not in DIMENSIONS or not q:
            continue
        if dim not in seen:
            seen[dim] = {
                "dimension": dim,
                "question": q,
                "hint": str(item.get("hint", "")).strip(),
            }
    result = []
    for dim in DIMENSIONS:
        if dim in seen:
            result.append(seen[dim])
        else:
            result.append({
                "dimension": dim,
                "question": DEFAULT_QUESTIONS[dim]["question"],
                "hint": DEFAULT_QUESTIONS[dim]["hint"],
            })
    return result


async def generate_questions(client: LLMClient, idea: str) -> list[dict]:
    """生成 8 个需求澄清问题（保证 ≥8 问，PRD 10.2 验收标准）。

    JSON 完全不可解析时全量兜底默认 8 问，保证主链路不断。
    """
    user = f"用户的产品想法：\n{idea}\n\n请围绕 8 个维度各生成 1 个针对该想法的澄清问题。"
    text = await client.complete(CLARIFY_SYSTEM, user, max_tokens=2000, temperature=0.6)
    try:
        data = extract_json(text)
        questions = _normalize_questions(data.get("questions"))
    except LLMError:
        questions = [
            {"dimension": d, "question": DEFAULT_QUESTIONS[d]["question"],
             "hint": DEFAULT_QUESTIONS[d]["hint"]}
            for d in DIMENSIONS
        ]
    return questions


def _qa_text(qa_list: list[dict]) -> str:
    lines = []
    for i, qa in enumerate(qa_list, 1):
        ans = (qa.get("answer") or "").strip()
        ans = ans if ans else "（用户跳过，待确认）"
        lines.append(f"{i}. {qa.get('dimension', '')}：{qa.get('question', '')}\n   回答：{ans}")
    return "\n".join(lines)


async def generate_brief(client: LLMClient, idea: str, qa_list: list[dict]) -> dict:
    """根据想法 + 澄清问答生成结构化需求摘要（RequirementBrief 字段）。"""
    user = (
        f"用户的产品想法：\n{idea}\n\n"
        f"需求澄清问答：\n{_qa_text(qa_list)}\n\n"
        "请生成结构化需求摘要。"
    )
    text = await client.complete(BRIEF_SYSTEM, user, max_tokens=2500, temperature=0.5)
    try:
        data = extract_json(text)
    except LLMError as first_err:
        # 纠错重试一次：把“输出不是合法 JSON”回传模型；二次失败才抛错
        retry_user = (
            user + "\n\n"
            f"你上一次的输出不是合法 JSON（错误：{first_err.message}）。"
            "请严格只输出一个 JSON 对象，不要任何解释或代码块标记。"
        )
        text = await client.complete(BRIEF_SYSTEM, retry_user, max_tokens=2500, temperature=0.4)
        data = extract_json(text)
    brief = {}
    for field in BRIEF_FIELDS:
        val = str(data.get(field, "")).strip()
        brief[field] = val if val else ("待确认" if field != "open_questions" else "无")
    return brief
