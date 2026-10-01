"""SQLAlchemy 数据模型（M1 子集）：User / Project / ClarificationQA / RequirementBrief / Task。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.config import DEFAULT_USER_ID


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """用户（MVP 匿名本地用户，预埋迁移）。"""
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Project(Base):
    """孵化项目。current_stage 枚举：idea→clarify→competitor→position→prd→tasks→package（MVP 范围并入 PRD「版本规划」章节，无独立 mvp 阶段）。"""
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    idea: Mapped[str] = mapped_column(Text)
    goal_type: Mapped[str] = mapped_column(String(32), default="real")  # course/portfolio/real/team_review
    default_competitor_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    current_stage: Mapped[str] = mapped_column(String(32), default="clarify")
    status: Mapped[str] = mapped_column(String(32), default="active")  # draft/active/done
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ClarificationQA(Base):
    """需求澄清问答（每轮 8 问，最多 2 轮）。"""
    __tablename__ = "clarification_qa"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    round_num: Mapped[int] = mapped_column(Integer, default=1)
    dimension: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    hint: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class RequirementBrief(Base):
    """结构化需求摘要（结构 = PRD 11.3 RequirementBrief 字段）。"""
    __tablename__ = "requirement_briefs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    one_liner: Mapped[str] = mapped_column(Text, default="")
    target_users: Mapped[str] = mapped_column(Text, default="")
    scenarios: Mapped[str] = mapped_column(Text, default="")
    pains: Mapped[str] = mapped_column(Text, default="")
    goals: Mapped[str] = mapped_column(Text, default="")
    non_goals: Mapped[str] = mapped_column(Text, default="")
    success_metrics: Mapped[str] = mapped_column(Text, default="")
    external_systems: Mapped[str] = mapped_column(Text, default="")
    knowledge_sources: Mapped[str] = mapped_column(Text, default="")
    open_questions: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft/confirmed
    source: Mapped[str] = mapped_column(String(32), default="clarify")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ProductDoc(Base):
    """PRD 结构化文档（PRD 11.5）：sections/evidence_refs 存 JSON 文本。"""
    __tablename__ = "product_docs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True, default=DEFAULT_USER_ID)
    doc_type: Mapped[str] = mapped_column(String(32), default="prd")
    version: Mapped[int] = mapped_column(Integer, default=1)
    sections: Mapped[str] = mapped_column(Text, default="[]")  # JSON [{title, content, evidence_refs[], status}]
    evidence_refs: Mapped[str] = mapped_column(Text, default="[]")  # JSON [ref_key, ...]
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft/confirmed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class DevTask(Base):
    """研发任务（PRD 11.6），注意与异步 Task 表区分。"""
    __tablename__ = "dev_tasks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True, default=DEFAULT_USER_ID)
    module: Mapped[str] = mapped_column(String(32))  # 前端/后端/AI/数据/集成/测试
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(8), default="P1")  # P0/P1/P2
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="")
    dependencies: Mapped[str] = mapped_column(Text, default="[]")  # JSON [任务标题]
    source_refs: Mapped[str] = mapped_column(Text, default="[]")  # JSON [PRD章节名或ref_key]
    export_status: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Task(Base):
    """异步 LLM 任务（提交 + 轮询状态 + 取结果），状态先落库、崩溃可恢复。

    注意区分：本表是后端异步执行任务（harness 内部）；PRD 11.6 的 DevTask（研发任务拆解）
    是产品业务实体，两者不同表、不共用。
    """
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("projects.id"), nullable=True, index=True)
    task_type: Mapped[str] = mapped_column(String(32))  # clarify_questions / brief
    status: Mapped[str] = mapped_column(String(32), default="queued")  # queued/processing/success/failed
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Competitor(Base):
    """竞品（PRD 11.4）。竞品由用户自选，MVP 最多 3 个。"""
    __tablename__ = "competitors"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True, default=DEFAULT_USER_ID)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text, default="")
    positioning: Mapped[str] = mapped_column(Text, default="")
    target_users: Mapped[str] = mapped_column(Text, default="")
    key_features: Mapped[str] = mapped_column(Text, default="")
    strengths: Mapped[str] = mapped_column(Text, default="")
    gaps: Mapped[str] = mapped_column(Text, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class CompetitorEvidence(Base):
    """竞品证据卡（PRD 4.4/11.4）：source_url 必填 + 格式校验。"""
    __tablename__ = "competitor_evidences"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    competitor_id: Mapped[str] = mapped_column(String(32), ForeignKey("competitors.id"), index=True)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True, default=DEFAULT_USER_ID)
    ref_key: Mapped[str] = mapped_column(String(32))  # 供定位/PRD 引用的短键（如 E1）
    source_type: Mapped[str] = mapped_column(String(32))  # 官网/官方文档/公开文章/用户输入
    source_url: Mapped[str] = mapped_column(Text)  # 必填，http/https
    evidence_type: Mapped[str] = mapped_column(String(32))  # 定位/功能/流程/集成/输出物/定价/用户/限制
    raw_excerpt: Mapped[str] = mapped_column(Text, default="")
    structured_claim: Mapped[str] = mapped_column(Text, default="")
    implication: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(32), default="待核查")  # 已确认/合理推断/用户补充/待核查
    used_in: Mapped[str] = mapped_column(Text, default="")  # 引用位置（逗号分隔，如 定位/PRD）
    fetched_at: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Positioning(Base):
    """产品定位与差异点（PRD 10.4）。differentiators/comparison/evidence_refs 存 JSON 文本。"""
    __tablename__ = "positionings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True, default=DEFAULT_USER_ID)
    one_liner: Mapped[str] = mapped_column(Text, default="")
    target_users: Mapped[str] = mapped_column(Text, default="")
    value_proposition: Mapped[str] = mapped_column(Text, default="")
    differentiators: Mapped[str] = mapped_column(Text, default="[]")  # JSON [{point, evidence_refs[]}]
    non_goals: Mapped[str] = mapped_column(Text, default="")
    comparison: Mapped[str] = mapped_column(Text, default="[]")  # JSON [{dimension, competitors{竞品名:事实}, our_product}]
    evidence_refs: Mapped[str] = mapped_column(Text, default="[]")  # JSON [ref_key, ...]
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft/confirmed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class DecisionLog(Base):
    """决策记忆（PRD 11.7）。记录每个关键决策的结论与依据。系统级决策 project_id 为空。"""
    __tablename__ = "decision_logs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("projects.id"), index=True, nullable=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True, default=DEFAULT_USER_ID)
    decision: Mapped[str] = mapped_column(Text)  # 决策内容
    reason: Mapped[str] = mapped_column(Text, default="")  # 决策原因
    source: Mapped[str] = mapped_column(String(32), default="")  # 来源（澄清/定位/PRD/任务/用户反馈）
    evidence_refs: Mapped[str] = mapped_column(Text, default="[]")  # JSON [ref_key, ...]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Feedback(Base):
    """用户/老师反馈（PRD 11.8），支撑迭代记录页。"""
    __tablename__ = "feedbacks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True, default=DEFAULT_USER_ID)
    content: Mapped[str] = mapped_column(Text)  # 反馈内容
    affected_sections: Mapped[str] = mapped_column(Text, default="")  # 影响章节（逗号分隔）
    author_type: Mapped[str] = mapped_column(String(32), default="user")  # 老师/用户/系统
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Export(Base):
    """导出记录（PRD 11.9），支撑导出埋点与漏斗指标。"""
    __tablename__ = "exports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True, default=DEFAULT_USER_ID)
    channel: Mapped[str] = mapped_column(String(32))  # markdown / feishu_copy / github_issue
    status: Mapped[str] = mapped_column(String(32), default="success")  # success / failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
