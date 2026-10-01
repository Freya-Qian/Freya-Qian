"""需求摘要生成、编辑与确认测试。"""
from __future__ import annotations

import asyncio

from app.services import task_worker
from app.services.prompts import BRIEF_FIELDS


def _create_project(client):
    r = client.post("/api/v1/projects", json={"name": "番茄钟", "idea": "做一个番茄钟 App", "goal_type": "real"})
    return r.json()


def _gen_questions_and_answer(client, project_id):
    task_id = client.post(f"/api/v1/projects/{project_id}/clarify/questions").json()["id"]
    asyncio.run(task_worker.process_task(task_id))
    qs = client.get(f"/api/v1/projects/{project_id}/clarify/questions").json()
    answers = [{"question_id": q["id"], "answer": "测试回答"} for q in qs]
    client.post(f"/api/v1/projects/{project_id}/clarify/answers", json={"answers": answers})


def test_brief_generate_and_get(client):
    p = _create_project(client)
    _gen_questions_and_answer(client, p["id"])

    r = client.post(f"/api/v1/projects/{p['id']}/brief")
    assert r.status_code == 202
    task_id = r.json()["id"]
    asyncio.run(task_worker.process_task(task_id))

    r = client.get(f"/api/v1/tasks/{task_id}")
    assert r.json()["status"] == "success"

    r = client.get(f"/api/v1/projects/{p['id']}/brief")
    assert r.status_code == 200
    b = r.json()
    assert b["version"] == 1
    assert b["status"] == "draft"
    for f in BRIEF_FIELDS:
        assert b[f] == f"{f}内容"


def test_brief_not_found_before_generate(client):
    p = _create_project(client)
    r = client.get(f"/api/v1/projects/{p['id']}/brief")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_brief_edit_and_confirm(client):
    p = _create_project(client)
    _gen_questions_and_answer(client, p["id"])
    asyncio.run(task_worker.process_task(client.post(f"/api/v1/projects/{p['id']}/brief").json()["id"]))

    # 编辑 + 确认
    r = client.put(f"/api/v1/projects/{p['id']}/brief", json={
        "one_liner": "一句话定义改过", "confirm": True,
    })
    assert r.status_code == 200
    b = r.json()
    assert b["one_liner"] == "一句话定义改过"
    assert b["status"] == "confirmed"

    # 项目阶段推进到竞品证据
    r = client.get(f"/api/v1/projects/{p['id']}")
    assert r.json()["current_stage"] == "competitor"


def test_brief_confirm_preserves_fields(client):
    """只发 confirm 不重新发字段时，字段不应被清空（partial update）。"""
    p = _create_project(client)
    _gen_questions_and_answer(client, p["id"])
    asyncio.run(task_worker.process_task(client.post(f"/api/v1/projects/{p['id']}/brief").json()["id"]))
    r = client.put(f"/api/v1/projects/{p['id']}/brief", json={"confirm": True})
    assert r.status_code == 200
    assert r.json()["one_liner"] == "one_liner内容"  # 未被清空
    assert r.json()["status"] == "confirmed"


def test_task_not_found(client):
    r = client.get("/api/v1/tasks/not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_brief_requires_key_items(client):
    """必答项（目标用户/场景/成功指标）未答时，生成摘要应 422。"""
    p = _create_project(client)
    task_id = client.post(f"/api/v1/projects/{p['id']}/clarify/questions").json()["id"]
    asyncio.run(task_worker.process_task(task_id))
    qs = client.get(f"/api/v1/projects/{p['id']}/clarify/questions").json()
    # 只回答选答项，必答项留空
    answers = [{"question_id": q["id"], "answer": "x"} for q in qs if not q["required"]]
    client.post(f"/api/v1/projects/{p['id']}/clarify/answers", json={"answers": answers})
    r = client.post(f"/api/v1/projects/{p['id']}/brief")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_INPUT"
    assert "必答" in r.json()["error"]["message"]


def test_brief_idempotent(client):
    p = _create_project(client)
    _gen_questions_and_answer(client, p["id"])
    r1 = client.post(f"/api/v1/projects/{p['id']}/brief")
    assert r1.status_code == 202
    r2 = client.post(f"/api/v1/projects/{p['id']}/brief")
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "CONFLICT"
