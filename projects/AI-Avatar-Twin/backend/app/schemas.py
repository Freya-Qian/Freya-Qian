"""输入输出 Pydantic 结构（M2 扩展：账户/项目/Profile/信息源）。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------- 账户 ----------


class AuthCodeRequest(BaseModel):
    phone: str = Field(..., min_length=5, max_length=20)


class AuthVerifyRequest(BaseModel):
    phone: str = Field(..., min_length=5, max_length=20)
    code: str = Field(..., min_length=4, max_length=10)


class UserOut(BaseModel):
    id: str
    phone: str


class AuthVerifyResponse(BaseModel):
    token: str
    user: UserOut


# ---------- 项目 ----------


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class ProjectUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class ProjectOut(BaseModel):
    id: str
    name: str
    default_avatar_profile_id: str | None = None
    status: str


# ---------- 数字人 Profile ----------


class ProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    avatar_type: str = Field(default="template")
    template_id: int = Field(default=1, strict=True, ge=1, le=3)
    voice_type: str = Field(default="default_tts")
    style_tags: list[str] = []
    language: str = Field(default="zh")
    catchphrases: list[str] = []
    banned_phrases: list[str] = []
    topic_preferences: list[str] = []
    platform_preferences: list[str] = []
    video_ratio: str = Field(default="9:16")


class ProfileUpdate(BaseModel):
    name: str | None = None
    avatar_type: str | None = None
    template_id: int | None = Field(default=None, strict=True, ge=1, le=3)
    voice_type: str | None = None
    style_tags: list[str] | None = None
    language: str | None = None
    catchphrases: list[str] | None = None
    banned_phrases: list[str] | None = None
    topic_preferences: list[str] | None = None
    platform_preferences: list[str] | None = None
    video_ratio: str | None = None


class ProfileOut(BaseModel):
    id: str
    project_id: str
    name: str
    avatar_type: str
    template_id: int = 1
    voice_type: str
    style_tags: list[str] = []
    language: str
    catchphrases: list[str] = []
    banned_phrases: list[str] = []
    topic_preferences: list[str] = []
    platform_preferences: list[str] = []
    video_ratio: str


# ---------- 信息源 ----------


class SourceCreate(BaseModel):
    project_id: str = Field(..., min_length=1)
    source_type: str = Field(..., pattern="^(url|manual|rss)$")
    name: str = Field(default="")
    url: str = Field(default="")
    content: str = Field(default="")


class SourceUpdate(BaseModel):
    name: str | None = None
    status: str | None = None


class SourceOut(BaseModel):
    id: str
    project_id: str
    source_type: str
    name: str
    url: str
    status: str


# ---------- M1 实体 ----------


class SourceItemOut(BaseModel):
    id: str
    source_type: str
    source_name: str
    original_url: str
    title: str
    published_at: str | None = None
    summary: str
    keywords: list[str] = []
    is_official: bool = False
    cross_check_count: int = 0
    credibility_score: int = 0
    video_potential_score: int = 0
    status: str


class TopicOut(BaseModel):
    id: str
    source_item_id: str
    title: str
    angle: str
    one_liner: str
    summary: str
    key_facts: list[str] = []
    source_urls: list[str] = []
    score: int = 0
    score_breakdown: dict[str, Any] = {}
    risk_level: str
    risk_flags: list[str] = []
    status: str


class ScriptOut(BaseModel):
    id: str
    topic_id: str
    duration_target: int
    platform: str
    language: str
    content: str
    fact_claims: list[str] = []
    risk_flags: list[str] = []
    source_urls: list[str] = []
    version: int
    status: str


class ScriptUpdate(BaseModel):
    content: str = Field(..., min_length=1)


class RevertRequest(BaseModel):
    version: int = Field(..., ge=1)


class ScriptVersionOut(BaseModel):
    version: int
    content: str
    created_at: Any


class VideoOut(BaseModel):
    id: str
    script_id: str
    avatar_profile_id: str | None = None
    version: int
    video_url: str = ""
    cover_url: str = ""
    subtitle_url: str = ""
    export_package_url: str = ""
    status: str
    error_message: str = ""


class VideoCreate(BaseModel):
    avatar_profile_id: str | None = None


class AgentRunRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=2000)
    profile_id: str | None = None
    project_id: str | None = None
