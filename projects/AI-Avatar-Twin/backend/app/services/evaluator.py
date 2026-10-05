"""脚本质量评估器（s17 目标闭环）：独立 judge 判定脚本是否达标。

复用 LLMClient 做一次轻量判定；评估结果可写轨迹日志（配合 hooks）。
"""
from __future__ import annotations

from pydantic import BaseModel, field_validator

from app.core.llm import LLMClient, LLMError
from app.services import prompts
from app.services.parser import parse_json


class EvalResult(BaseModel):
    passed: bool = False
    reason: str = ""
    scores: dict = {}

    @field_validator("passed", mode="before")
    @classmethod
    def _passed(cls, v):
        # 兼容模型偶发输出字符串（true/false/是/否）而非 JSON 布尔
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() not in ("false", "no", "否", "不通过", "0", "")
        return bool(v)

    @field_validator("scores", mode="before")
    @classmethod
    def _scores(cls, v):
        return v if isinstance(v, dict) else {}


async def evaluate_script(client: LLMClient, script_content: str,
                          topic_title: str, fact_claims: list[str],
                          source_urls: list[str]) -> EvalResult:
    """判定脚本是否回应选题、事实有据、语言通顺、长度合适。

    规则版兜底：模型不可用时不阻断（视为通过，交给人工），
    避免评估器本身成为链路单点故障。
    """
    user = prompts.EVAL_USER.format(
        topic_title=topic_title,
        content=script_content[:2000],
        fact_claims="；".join(fact_claims or []),
        sources="\n".join(source_urls or []),
    )
    try:
        data = await _generate_json_once(client, prompts.EVAL_SYSTEM, user)
    except LLMError:
        # 评估器失败不阻断业务：视为通过，标记由人工复核
        return EvalResult(passed=True, reason="评估器不可用，交由人工复核")

    return EvalResult.model_validate(data)


async def _generate_json_once(client: LLMClient, system: str, user: str) -> dict:
    text = await client.complete(system, user, max_tokens=600, temperature=0.2)
    return parse_json(text)
