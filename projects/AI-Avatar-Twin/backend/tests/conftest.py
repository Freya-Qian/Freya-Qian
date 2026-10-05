"""测试共用夹具：临时数据库 + FakeLLMClient + 抓取/RSS mock。"""
from __future__ import annotations

import json

import pytest
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.llm import LLMError
from app.main import app
from app.services import fetcher as fetcher_mod

from app import models  # noqa: F401  确保模型已注册


def make_summary():
    return {
        "title": "OpenAI 发布新模型",
        "summary": "OpenAI 发布了新一代模型，能力更强，适合开发者使用。",
        "keywords": ["OpenAI", "模型", "AI"],
        "is_official": True,
        "credibility_score": 90,
        "video_potential_score": 85,
    }


def make_topic(i=0):
    return {
        "title": f"选题 {i}：OpenAI 新模型意味着什么",
        "angle": "从开发者视角解读新模型的实际影响",
        "one_liner": "一句话看点：新模型到底强在哪",
        "key_facts": ["OpenAI 发布新模型", "价格更低"],
        "source_urls": ["https://example.com/news"],
        "score": 80 - i,
        "score_breakdown": {"新鲜度": 90, "重要性": 85, "受众相关性": 80, "视频化潜力": 82, "观点空间": 75, "风险": 20},
        "risk_level": "low",
        "risk_flags": [],
    }


def make_script():
    return {
        "content": "【开头钩子】今天 OpenAI 放大招了。\n【核心事实】它发布了新模型。",
        "fact_claims": ["OpenAI 发布新模型"],
        "risk_flags": ["单一来源"],
        "source_urls": ["https://example.com/news"],
    }


class FakeLLMClient:
    def __init__(self, fail: str | None = None):
        self.fail = fail

    async def complete(self, system, user, max_tokens=2000, temperature=0.6):
        if self.fail == "NO_API_KEY":
            raise LLMError("NO_API_KEY", "未配置模型 API Key")
        if "选题策划" in system:
            return json.dumps({"topics": [make_topic(i) for i in range(3)]}, ensure_ascii=False)
        if "口播撰稿人" in system:
            return json.dumps(make_script(), ensure_ascii=False)
        return json.dumps(make_summary(), ensure_ascii=False)

    async def stream(self, system, user, max_tokens=2000, temperature=0.6):
        if self.fail == "NO_API_KEY":
            raise LLMError("NO_API_KEY", "未配置模型 API Key")
        text = json.dumps(make_script(), ensure_ascii=False)
        for i in range(0, len(text), 15):
            yield text[i : i + 15]


async def _fake_fetch(url: str):
    url = fetcher_mod.validate_url(url)
    return {"title": "测试标题", "source_name": "example.com", "content_text": "这是正文。" * 200}


class _FakeEntry:
    def __init__(self, i):
        self.link = f"https://example.com/rss-{i}"
        self.title = f"RSS 条目标题 {i}"
        self.summary = "RSS 条目摘要"


class _FakeFeed:
    bozo = 0
    entries = [_FakeEntry(i) for i in range(3)]


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    from app.services import engine as engine_mod
    import feedparser

    fake_client = FakeLLMClient()
    monkeypatch.setattr(engine_mod, "_client", lambda: fake_client)
    monkeypatch.setattr(fetcher_mod, "fetch_url", _fake_fetch)
    async def fake_response(url):
        fetcher_mod.validate_url(url)
        return httpx.Response(200, content=b"<rss/>")
    monkeypatch.setattr(fetcher_mod, "fetch_response", fake_response)
    monkeypatch.setattr(feedparser, "parse", lambda content: _FakeFeed())

    with TestClient(app) as c:
        c.fake_client = fake_client
        yield c

    app.dependency_overrides.clear()
