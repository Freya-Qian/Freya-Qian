"""Pydantic 输入输出结构。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# 合法 goal_type 与示例想法（PRD 10.1 / 5.3 冷启动）
GOAL_TYPES = {"course": "课程作业", "portfolio": "作品集", "real": "真实开发", "team_review": "团队评审"}
SAMPLE_IDEAS = [
    {"name": "番茄钟 App", "idea": "做一个帮助专注学习的番茄钟 App，支持任务拆分和统计"},
    {"name": "二手书交换平台", "idea": "做一个校园二手书交换平台，学生可以发布闲置书并交换"},
    {"name": "AI 周报助手", "idea": "做一个把聊天记录自动整理成工作周报的助手"},
]


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    idea: str = Field(..., min_length=1, max_length=5000)
    goal_type: str = Field("real")


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    idea: str
    goal_type: str
    default_competitor_id: str | None
    current_stage: str
    status: str
    created_at: datetime
    updated_at: datetime


class QuestionOut(BaseModel):
    id: str
    round_num: int
    dimension: str
    question: str
    hint: str
    answer: str
    skipped: bool
    required: bool = False


class AnswerIn(BaseModel):
    question_id: str
    answer: str = ""


class AnswersIn(BaseModel):
    answers: list[AnswerIn] = Field(..., min_length=1)


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str | None
    task_type: str
    status: str
    error: str
    result_json: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class BriefFields(BaseModel):
    one_liner: str = ""
    target_users: str = ""
    scenarios: str = ""
    pains: str = ""
    goals: str = ""
    non_goals: str = ""
    success_metrics: str = ""
    external_systems: str = ""
    knowledge_sources: str = ""
    open_questions: str = ""


class BriefUpdate(BriefFields):
    confirm: bool = False


class BriefOut(BriefFields):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    version: int
    status: str
    created_at: datetime
    updated_at: datetime


# ── M2 竞品证据与定位 ──

class CompetitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    url: str
    positioning: str
    target_users: str
    key_features: str
    strengths: str
    gaps: str
    is_default: bool


class CompetitorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    url: str = ""
    positioning: str = ""
    target_users: str = ""
    key_features: str = ""
    strengths: str = ""
    gaps: str = ""


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    competitor_id: str
    ref_key: str
    source_type: str
    source_url: str
    evidence_type: str
    raw_excerpt: str
    structured_claim: str
    implication: str
    confidence: str
    used_in: str
    fetched_at: str


class EvidenceCreate(BaseModel):
    source_type: str = "用户输入"
    source_url: str
    evidence_type: str = "定位"
    raw_excerpt: str = ""
    structured_claim: str
    implication: str = ""
    confidence: str = "待核查"
    fetched_at: str = ""


class EvidenceUpdate(BaseModel):
    """修改证据卡（字段可选，None 表示不修改）。"""
    source_type: str | None = None
    source_url: str | None = None
    evidence_type: str | None = None
    raw_excerpt: str | None = None
    structured_claim: str | None = None
    implication: str | None = None
    confidence: str | None = None
    fetched_at: str | None = None


class EvidenceFetchIn(BaseModel):
    """贴网址抓取：用户提供一个竞品网页链接，可指定来源类型。"""
    url: str
    source_type: str = "公开文章"  # 官网/官方文档/公开文章/用户输入（下单时由用户选，后端校验）


class PositioningOut(BaseModel):
    id: str
    project_id: str
    one_liner: str
    target_users: str
    value_proposition: str
    differentiators: list[dict]
    non_goals: str
    comparison: list[dict]
    evidence_refs: list[str]
    version: int
    status: str
    created_at: datetime
    updated_at: datetime


class PositioningUpdate(BaseModel):
    one_liner: str = ""
    target_users: str = ""
    value_proposition: str = ""
    non_goals: str = ""
    confirm: bool = False


# ── M3 PRD 与任务拆解 ──

class PrdOut(BaseModel):
    id: str
    project_id: str
    version: int
    status: str
    sections: list[dict]
    evidence_refs: list[str]
    created_at: datetime
    updated_at: datetime


class PrdUpdate(BaseModel):
    sections: list[dict] | None = None
    confirm: bool = False


class DevTaskOut(BaseModel):
    id: str
    module: str
    title: str
    description: str
    priority: str
    acceptance_criteria: str
    dependencies: list[str]
    source_refs: list[str]
    export_status: str


class DevTaskUpdate(BaseModel):
    """编辑单个研发任务（字段可选，None 表示不修改）。"""
    title: str | None = None
    description: str | None = None
    acceptance_criteria: str | None = None
    priority: str | None = None   # 限 P0/P1/P2
    module: str | None = None     # 限【前端/后端/AI/数据/集成/测试】


# ── M4 迭代记录与导出埋点（PRD 11.7/11.8/11.9） ──

class DecisionLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str | None
    decision: str
    reason: str
    source: str
    evidence_refs: str
    created_at: datetime


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    content: str
    affected_sections: str
    author_type: str
    created_at: datetime


class FeedbackCreate(BaseModel):
    content: str = Field(..., min_length=1)
    affected_sections: str = ""
    author_type: str = "user"  # 老师/用户/系统


class ExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    channel: str
    status: str
    created_at: datetime


class ExportCreate(BaseModel):
    channel: str = "markdown"  # markdown / feishu_copy / github_issue


class ExportResult(BaseModel):
    export_id: str
    channel: str
    title: str
    content: str


# ── 设置页模型配置（阶段 3 配套）──

class ModelSettingsUpdate(BaseModel):
    model_api_key: str = Field(..., min_length=1)
    model_name: str | None = None
    model_base_url: str | None = None
