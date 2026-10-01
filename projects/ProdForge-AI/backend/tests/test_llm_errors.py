"""LLM 调用失败与兜底路径测试。"""
from __future__ import annotations

import asyncio

import pytest

from app.core.llm import LLMError
from app.services import task_worker


def _create_project(client):
    return client.post("/api/v1/projects", json={"name": "x", "idea": "y", "goal_type": "real"}).json()


class _NoKeyClient:
    async def complete(self, system, user, max_tokens=2000, temperature=0.6):
        raise LLMError("NO_API_KEY", "未配置模型 API Key")


def test_task_fails_with_no_api_key(client, monkeypatch):
    monkeypatch.setattr(task_worker, "LLMClient", lambda: _NoKeyClient())
    p = _create_project(client)
    task_id = client.post(f"/api/v1/projects/{p['id']}/clarify/questions").json()["id"]

    asyncio.run(task_worker.process_task(task_id))

    r = client.get(f"/api/v1/tasks/{task_id}")
    assert r.json()["status"] == "failed"
    assert r.json()["error"] == "未配置模型 API Key"


def test_missing_questions_field_gets_default_fallback(monkeypatch):
    """模型返回空 questions 时，确定性兜底补齐 8 问（不抛错、不重试）。"""
    from app.services import clarify

    class _EmptyClient:
        async def complete(self, system, user, max_tokens=2000, temperature=0.6):
            return '{"questions": []}'

    async def _go():
        qs = await clarify.generate_questions(_EmptyClient(), "一个想法")
        return qs

    qs = asyncio.run(_go())
    assert len(qs) == 8
    # 兜底问题来自默认模板
    assert all(q["question"] for q in qs)


def test_questions_fallback_when_json_unparseable():
    """JSON 完全不可解析时，全量兜底默认 8 问，主链路不断。"""
    from app.services import clarify

    class _BadClient:
        async def complete(self, system, user, max_tokens=2000, temperature=0.6):
            return "抱歉，我暂时无法生成问题"  # 完全不是 JSON

    qs = asyncio.run(clarify.generate_questions(_BadClient(), "一个想法"))
    assert len(qs) == 8
    assert all(q["question"] for q in qs)
