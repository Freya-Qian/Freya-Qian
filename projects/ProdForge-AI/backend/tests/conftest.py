"""测试共用夹具：临时内存数据库 + FakeLLMClient + worker 打桩。"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Redirect before importing main: its module-level init_db must never touch user data.
from app import config

_bootstrap_dir = TemporaryDirectory(prefix="product-factory-tests-")
config.DB_PATH = Path(_bootstrap_dir.name) / "bootstrap.db"

from app import models  # noqa: F401  确保模型已注册
from app.core.db import Base, enable_foreign_keys, get_db
from app import main
from app.main import app
from app.services import fetcher, task_worker
from app.services.prompts import (
    BRIEF_FIELDS,
    BRIEF_SYSTEM,
    CLARIFY_SYSTEM,
    COMPETITOR_RECOMMEND_SYSTEM,
    DIMENSIONS,
    EVIDENCE_FETCH_SYSTEM,
    POSITIONING_SYSTEM,
    PRD_CHAPTERS,
    PRD_SYSTEM,
    TASKS_SYSTEM,
)


class FakeLLMClient:
    """按 system prompt 常量返回对应结构的假 JSON（prompt 改动也不断）。"""

    def __init__(self):
        self.last_usage = {}

    async def complete(self, system, user, max_tokens=2000, temperature=0.6):
        if system == CLARIFY_SYSTEM:
            questions = [
                {"dimension": d, "question": f"关于「{d}」，你的想法是什么？", "hint": f"{d}的回答提示"}
                for d in DIMENSIONS
            ]
            return json.dumps({"questions": questions}, ensure_ascii=False)
        if system == BRIEF_SYSTEM:
            brief = {f: f"{f}内容" for f in BRIEF_FIELDS}
            return json.dumps(brief, ensure_ascii=False)
        if system == POSITIONING_SYSTEM:
            return json.dumps({
                "one_liner": "Web 端 AI 产品孵化工作台",
                "target_users": "产品经理、独立开发者、AI 学习者",
                "value_proposition": "把模糊想法变成可评审可开发的资料包",
                "differentiators": [
                    {"point": "聚焦产品孵化垂直场景", "evidence_refs": ["E1"]},
                    {"point": "固定阶段流水线可验收", "evidence_refs": ["E2"]},
                ],
                "non_goals": "不做通用办公、不做多专家矩阵",
                "comparison": [
                    {"dimension": "定位", "competitors": {"Forest": "全场景办公"}, "our_product": "垂直产品孵化"},
                    {"dimension": "用户", "competitors": {"Forest": "各职能职场人"}, "our_product": "产品经理/独立开发者"},
                ],
                "evidence_refs": ["E1", "E2"],
            }, ensure_ascii=False)
        if system == EVIDENCE_FETCH_SYSTEM:
            return json.dumps({
                "evidence_type": "功能",
                "structured_claim": "支持专注计时与统计",
                "implication": "可借鉴专注计时能力",
                "raw_excerpt": "专注计时是核心功能",
                "confidence": "合理推断",
            }, ensure_ascii=False)
        if system == COMPETITOR_RECOMMEND_SYSTEM:
            return json.dumps({
                "competitors": [
                    {"name": "Forest", "url": "https://forestapp.cc", "positioning": "专注计时"},
                    {"name": "Focus To-Do", "url": "https://www.focustodo.cn", "positioning": "番茄钟+待办"},
                ],
            }, ensure_ascii=False)
        if system == PRD_SYSTEM:
            return json.dumps({
                "sections": [
                    {"title": t, "content": f"{t}内容",
                     "evidence_refs": ["E1"] if t in ["产品定位", "竞品证据与分析", "版本规划"] else []}
                    for t in PRD_CHAPTERS
                ],
                "evidence_refs": ["E1"],
            }, ensure_ascii=False)
        if system == TASKS_SYSTEM:
            return json.dumps({
                "tasks": [
                    {"module": "前端", "title": "项目列表页", "description": "d", "priority": "P0",
                     "acceptance_criteria": "a", "dependencies": [], "source_refs": ["功能需求"]},
                    {"module": "后端", "title": "项目创建接口", "description": "d", "priority": "P0",
                     "acceptance_criteria": "a", "dependencies": ["项目列表页"], "source_refs": ["功能需求"]},
                    {"module": "AI", "title": "需求澄清生成", "description": "d", "priority": "P0",
                     "acceptance_criteria": "a", "dependencies": [], "source_refs": ["功能需求"]},
                    {"module": "数据", "title": "SQLite 持久化", "description": "d", "priority": "P0",
                     "acceptance_criteria": "a", "dependencies": ["项目创建接口"], "source_refs": ["数据对象"]},
                    {"module": "测试", "title": "全链路验收", "description": "d", "priority": "P1",
                     "acceptance_criteria": "a", "dependencies": ["不存在的任务", "需求澄清生成"], "source_refs": ["验收标准"]},
                ],
            }, ensure_ascii=False)
        return "{}"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    from app.services import observability
    # 埋点重定向到临时文件，避免测试污染真实 data/events.jsonl
    monkeypatch.setattr(observability, "EVENTS_PATH", tmp_path / "events_test.jsonl")

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    event.listen(engine, "connect", enable_foreign_keys)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestingSession() as db:
        db.add(models.User(id=config.DEFAULT_USER_ID))
        db.commit()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # 打桩：worker 用测试库会话、假客户端、不自动入队（由测试显式 process_task）；抓取走假实现
    fake = FakeLLMClient()
    monkeypatch.setattr(task_worker, "SessionLocal", TestingSession)
    monkeypatch.setattr(task_worker, "LLMClient", lambda: fake)
    monkeypatch.setattr(task_worker, "enqueue", lambda task_id: None)
    monkeypatch.setattr(main, "SessionLocal", TestingSession)
    monkeypatch.setattr(task_worker, "start_worker", lambda: None)
    monkeypatch.setattr(task_worker, "stop_worker", lambda: None)

    async def _fake_fetch(url):
        return {"title": "测试竞品官网", "source_name": "example.com",
                "content_text": "这是竞品的功能描述，支持专注计时与统计。" * 20}

    monkeypatch.setattr(fetcher, "fetch_url", _fake_fetch)

    with TestClient(app) as c:
        c.fake_client = fake
        yield c

    app.dependency_overrides.clear()
    engine.dispose()
