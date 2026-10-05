"""素材包文案：标题 / 简介 / 标签（复用文字模型）。"""
from __future__ import annotations

from pydantic import BaseModel, field_validator

from app.core.llm import LLMClient
from app.services import engine, prompts


class PackagingResult(BaseModel):
    title: str = ""
    description: str = ""
    tags: list[str] = []

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, v):
        return [str(x) for x in v] if isinstance(v, list) else []


async def generate_packaging(client: LLMClient, content: str, topic_title: str, platform: str) -> PackagingResult:
    user = prompts.PACKAGING_USER.format(content=content[:1500], topic=topic_title, platform=platform)
    data = await engine._generate_json(client, prompts.PACKAGING_SYSTEM, user, max_tokens=600)
    return PackagingResult.model_validate(data)
