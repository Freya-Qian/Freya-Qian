"""需求澄清问题生成与回答测试（worker 显式 process_task + 假客户端）。"""
from __future__ import annotations

import asyncio

from app.services import task_worker
from app.services.prompts import DIMENSIONS


def _create_project(client):
    r = client.post("/api/v1/projects", json={"name": "番茄钟", "idea": "做一个番茄钟 App", "goal_type": "real"})
    assert r.status_code == 201
    return r.json()


def _run(task_id):
    asyncio.run(task_worker.process_task(task_id))


def test_generate_questions(client):
    p = _create_project(client)
    r = client.post(f"/api/v1/projects/{p['id']}/clarify/questions")
    assert r.status_code == 202
    task_id = r.json()["id"]

    _run(task_id)

    # 任务成功
    r = client.get(f"/api/v1/tasks/{task_id}")
    assert r.json()["status"] == "success"

    # 恰好 8 问，且覆盖 8 个维度
    r = client.get(f"/api/v1/projects/{p['id']}/clarify/questions")
    qs = r.json()
    assert len(qs) == 8
    assert {q["dimension"] for q in qs} == set(DIMENSIONS)


def test_submit_answers_and_skip(client):
    p = _create_project(client)
    task_id = client.post(f"/api/v1/projects/{p['id']}/clarify/questions").json()["id"]
    _run(task_id)
    qs = client.get(f"/api/v1/projects/{p['id']}/clarify/questions").json()

    answers = [
        {"question_id": qs[0]["id"], "answer": "学生群体"},
        {"question_id": qs[1]["id"], "answer": "自习时使用"},
        {"question_id": qs[2]["id"], "answer": ""},  # 留空 = 跳过
    ]
    r = client.post(f"/api/v1/projects/{p['id']}/clarify/answers", json={"answers": answers})
    assert r.status_code == 200
    got = {q["id"]: q for q in r.json()}
    assert got[qs[0]["id"]]["answer"] == "学生群体"
    assert got[qs[0]["id"]]["skipped"] is False
    assert got[qs[2]["id"]]["answer"] == ""
    assert got[qs[2]["id"]]["skipped"] is True


def test_submit_answer_bad_question_id(client):
    p = _create_project(client)
    r = client.post(
        f"/api/v1/projects/{p['id']}/clarify/answers",
        json={"answers": [{"question_id": "nope", "answer": "x"}]},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_INPUT"


def test_questions_before_generation_is_empty(client):
    p = _create_project(client)
    r = client.get(f"/api/v1/projects/{p['id']}/clarify/questions")
    assert r.status_code == 200
    assert r.json() == []


def test_generate_questions_idempotent(client):
    p = _create_project(client)
    r1 = client.post(f"/api/v1/projects/{p['id']}/clarify/questions")
    assert r1.status_code == 202
    # 任务尚未处理（测试中 worker 不自动执行，仍 queued）→ 重复提交应 409
    r2 = client.post(f"/api/v1/projects/{p['id']}/clarify/questions")
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "CONFLICT"
