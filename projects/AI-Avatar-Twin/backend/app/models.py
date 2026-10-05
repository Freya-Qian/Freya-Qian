"""数据模型：账户 / 项目 / 数字人 Profile / 信息源 + M1 实体挂 user_id（字段对齐 PRD 9.x）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _now() -> datetime:
    return datetime.now()


# ---------- 账户 ----------


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    phone: Mapped[str] = mapped_column(String(20), primary_key=True)
    code: Mapped[str] = mapped_column(String(10))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


# ---------- 项目 / Profile / 信息源 ----------


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    default_avatar_profile_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/archived
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AvatarProfile(Base):
    __tablename__ = "avatar_profiles"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    project_id: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    avatar_type: Mapped[str] = mapped_column(String(20), default="template")  # template/uploaded_self
    voice_type: Mapped[str] = mapped_column(String(20), default="default_tts")
    style_tags: Mapped[list] = mapped_column(JSON, default=list)
    language: Mapped[str] = mapped_column(String(20), default="zh")
    catchphrases: Mapped[list] = mapped_column(JSON, default=list)
    banned_phrases: Mapped[list] = mapped_column(JSON, default=list)
    topic_preferences: Mapped[list] = mapped_column(JSON, default=list)
    platform_preferences: Mapped[list] = mapped_column(JSON, default=list)
    video_ratio: Mapped[str] = mapped_column(String(10), default="9:16")
    avatar_asset_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    avatar_consent_status: Mapped[str] = mapped_column(String(20), default="none")  # none/granted
    template_id: Mapped[int] = mapped_column(Integer, default=1)  # 模板形象编号（avatar_type=template 时用）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    project_id: Mapped[str] = mapped_column(String(40), index=True)
    source_type: Mapped[str] = mapped_column(String(20))  # url/manual/rss
    name: Mapped[str] = mapped_column(String(200), default="")
    url: Mapped[str] = mapped_column(String(1000), default="")
    content: Mapped[str] = mapped_column(Text, default="")  # manual 源的正文
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/disabled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ---------- M1 实体（挂 user_id） ----------


class SourceItem(Base):
    __tablename__ = "source_items"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), default="url")
    source_name: Mapped[str] = mapped_column(String(200), default="")
    original_url: Mapped[str] = mapped_column(String(1000), default="")
    title: Mapped[str] = mapped_column(String(500), default="")
    content_text: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    summary: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    is_official: Mapped[bool] = mapped_column(Integer, default=0)
    cross_check_count: Mapped[int] = mapped_column(Integer, default=0)
    credibility_score: Mapped[int] = mapped_column(Integer, default=0)
    video_potential_score: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="fetched")  # fetched/summarized/failed


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    source_item_id: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    angle: Mapped[str] = mapped_column(String(500), default="")
    one_liner: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    key_facts: Mapped[list] = mapped_column(JSON, default=list)
    source_urls: Mapped[list] = mapped_column(JSON, default=list)
    score: Mapped[int] = mapped_column(Integer, default=0)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")  # low/medium/high
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="new")  # new/selected/scripted
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    topic_id: Mapped[str] = mapped_column(String(40), index=True)
    duration_target: Mapped[int] = mapped_column(Integer, default=30)
    platform: Mapped[str] = mapped_column(String(20), default="douyin")
    language: Mapped[str] = mapped_column(String(20), default="zh")
    content: Mapped[str] = mapped_column(Text, default="")
    fact_claims: Mapped[list] = mapped_column(JSON, default=list)
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    source_urls: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft/approved
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ScriptVersion(Base):
    __tablename__ = "script_versions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    script_id: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, default="")
    fact_claims: Mapped[list] = mapped_column(JSON, default=list)
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    source_urls: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class VideoProject(Base):
    __tablename__ = "video_projects"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    script_id: Mapped[str] = mapped_column(String(40), index=True)
    avatar_profile_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    video_url: Mapped[str] = mapped_column(String(500), default="")
    cover_url: Mapped[str] = mapped_column(String(500), default="")
    subtitle_url: Mapped[str] = mapped_column(String(500), default="")
    export_package_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued/rendering/success/failed
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class UserPreference(Base):
    """用户偏好记忆（s09）：选题偏好/忽略类型/历史表现，用于反向优化推荐。"""
    __tablename__ = "user_preferences"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    topic_preferences: Mapped[list] = mapped_column(JSON, default=list)  # 加权偏好
    ignored_topics: Mapped[list] = mapped_column(JSON, default=list)  # 被忽略的选题类型
    performance_history: Mapped[list] = mapped_column(JSON, default=list)  # 历史表现记录
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
