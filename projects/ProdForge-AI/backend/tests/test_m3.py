"""M3 PRD 生成与任务拆解测试。"""
from __future__ import annotations

import asyncio

from app.services import task_worker
from app.services.prompts import PRD_CHAPTERS


def _create_project(client):
    return client.post("/api/v1/projects", json={"name": "番茄钟", "idea": "做一个番茄钟", "goal_type": "real"}).json()


def _setup_brief(client, project_id):
    task_id = client.post(f"/api/v1/projects/{project_id}/clarify/questions").json()["id"]
    asyncio.run(task_worker.process_task(task_id))
    qs = client.get(f"/api/v1/projects/{project_id}/clarify/questions").json()
    client.post(f"/api/v1/projects/{project_id}/clarify/answers",
                json={"answers": [{"question_id": q["id"], "answer": "回答"} for q in qs]})
    asyncio.run(task_worker.process_task(client.post(f"/api/v1/projects/{project_id}/brief").json()["id"]))
    client.put(f"/api/v1/projects/{project_id}/brief", json={"confirm": True})


def _add_competitor_with_evidence(client, project_id):
    """添加竞品 + 2 张证据卡（ref_key E1/E2）。"""
    comp = client.post(f"/api/v1/projects/{project_id}/competitors",
                       json={"name": "Forest", "url": "https://forestapp.cc"}).json()
    for claim in ("结论1", "结论2"):
        client.post(f"/api/v1/projects/{project_id}/competitors/{comp['id']}/evidences",
                    json={"source_url": "https://forestapp.cc", "structured_claim": claim})
    return comp


def _setup_positioning(client, project_id, confirm=True):
    """需求澄清 + 竞品 + 定位（供 PRD 生成使用）。默认生成并确认定位。"""
    _setup_brief(client, project_id)
    _add_competitor_with_evidence(client, project_id)
    asyncio.run(task_worker.process_task(
        client.post(f"/api/v1/projects/{project_id}/positioning").json()["id"]))
    if confirm:
        client.put(f"/api/v1/projects/{project_id}/positioning", json={"confirm": True})


def _generate_and_confirm_prd(client, project_id):
    """生成并确认 PRD（供任务拆解测试使用）。"""
    asyncio.run(task_worker.process_task(
        client.post(f"/api/v1/projects/{project_id}/prd").json()["id"]))
    client.put(f"/api/v1/projects/{project_id}/prd", json={"confirm": True})


# ── PRD 生成与审计 ──

def test_prd_requires_positioning(client):
    """#1 状态机：未生成定位直接 start_prd → 409 NOT_READY。"""
    p = _create_project(client)
    r = client.post(f"/api/v1/projects/{p['id']}/prd")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NOT_READY"


def test_prd_requires_confirmed_positioning(client):
    """#1 状态机：已生成定位但未确认 → 409 NOT_READY。"""
    p = _create_project(client)
    _setup_positioning(client, p["id"], confirm=False)
    r = client.post(f"/api/v1/projects/{p['id']}/prd")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NOT_READY"


def test_prd_generate_and_get(client):
    p = _create_project(client)
    _setup_positioning(client, p["id"])
    r = client.post(f"/api/v1/projects/{p['id']}/prd")
    assert r.status_code == 202
    asyncio.run(task_worker.process_task(r.json()["id"]))

    r = client.get(f"/api/v1/projects/{p['id']}/prd")
    assert r.status_code == 200
    doc = r.json()
    assert doc["version"] == 1
    assert [s["title"] for s in doc["sections"]] == PRD_CHAPTERS  # 固定 11 章
    assert doc["evidence_refs"] == ["E1"]
    # 结论型章节有证据引用
    by_title = {s["title"]: s for s in doc["sections"]}
    assert by_title["产品定位"]["evidence_refs"] == ["E1"]
    assert by_title["产品定位"]["status"] == "ok"
    # 非结论型章节无证据 → status ok（不强制）
    assert by_title["核心流程"]["status"] == "ok"


def test_prd_confirm_moves_to_tasks(client):
    """#4 阶段枚举：PRD 确认后进入任务拆解（MVP 范围并入 PRD 章节，无独立 mvp 阶段）。"""
    p = _create_project(client)
    _setup_positioning(client, p["id"])
    asyncio.run(task_worker.process_task(client.post(f"/api/v1/projects/{p['id']}/prd").json()["id"]))
    r = client.put(f"/api/v1/projects/{p['id']}/prd", json={"confirm": True})
    assert r.json()["status"] == "confirmed"
    assert client.get(f"/api/v1/projects/{p['id']}").json()["current_stage"] == "tasks"


def test_update_prd_reaudits_refs(client):
    """#2 编辑 PRD 后重新审计：无效 ref_key 被过滤，结论型章节标待确认。"""
    p = _create_project(client)
    _setup_positioning(client, p["id"])
    asyncio.run(task_worker.process_task(client.post(f"/api/v1/projects/{p['id']}/prd").json()["id"]))
    doc = client.get(f"/api/v1/projects/{p['id']}/prd").json()
    sections = doc["sections"]
    for s in sections:
        if s["title"] == "产品定位":
            s["evidence_refs"] = ["E999"]  # 无效 ref_key
    r = client.put(f"/api/v1/projects/{p['id']}/prd", json={"sections": sections})
    assert r.status_code == 200
    updated = {s["title"]: s for s in r.json()["sections"]}
    assert updated["产品定位"]["evidence_refs"] == []  # 无效 ref 被过滤
    assert updated["产品定位"]["status"] == "待确认"


def test_audit_marks_unverified():
    """结论型章节无证据 → 标待确认；不存在的 ref_key 被过滤。"""
    from app.services.prd import audit_sections
    sections = [
        {"title": "产品定位", "content": "x", "evidence_refs": ["不存在"]},
        {"title": "核心流程", "content": "y", "evidence_refs": []},
    ]
    sections, unverified = audit_sections(sections, {"E1"})
    by = {s["title"]: s for s in sections}
    assert by["产品定位"]["evidence_refs"] == []  # 无效 ref 被过滤
    assert by["产品定位"]["status"] == "待确认"
    assert "产品定位" in unverified
    assert by["核心流程"]["status"] == "ok"  # 非结论型章节不强制


def test_prd_unverified_merged_into_content(client):
    """#3 无证据结论清单合并进 PRD 正文，用户在 PRD 详情可见。"""
    import json as _json

    from app.services.prompts import PRD_SYSTEM

    p = _create_project(client)
    _setup_positioning(client, p["id"])

    original = client.fake_client.complete

    async def fake_complete(system, user, max_tokens=2000, temperature=0.6):
        if system == PRD_SYSTEM:
            # 结论型章节均无证据 → 触发 unverified 清单
            return _json.dumps({
                "sections": [
                    {"title": t, "content": f"{t}内容", "evidence_refs": []}
                    for t in PRD_CHAPTERS
                ],
                "evidence_refs": [],
            }, ensure_ascii=False)
        return await original(system, user, max_tokens, temperature)

    client.fake_client.complete = fake_complete
    asyncio.run(task_worker.process_task(
        client.post(f"/api/v1/projects/{p['id']}/prd").json()["id"]))

    doc = client.get(f"/api/v1/projects/{p['id']}/prd").json()
    risk = next(s for s in doc["sections"] if s["title"] == "风险与待确认问题")
    assert "缺少证据支撑" in risk["content"]
    assert "产品定位" in risk["content"]
    client.fake_client.complete = original


# ── 任务拆解 ──

def test_tasks_requires_prd(client):
    p = _create_project(client)
    _setup_positioning(client, p["id"])
    r = client.post(f"/api/v1/projects/{p['id']}/tasks")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NOT_READY"


def test_tasks_requires_confirmed_prd(client):
    """#1 状态机：PRD 已生成但未确认 → 409 NOT_READY。"""
    p = _create_project(client)
    _setup_positioning(client, p["id"])
    asyncio.run(task_worker.process_task(client.post(f"/api/v1/projects/{p['id']}/prd").json()["id"]))
    r = client.post(f"/api/v1/projects/{p['id']}/tasks")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NOT_READY"


def test_tasks_generate_and_get(client):
    p = _create_project(client)
    _setup_positioning(client, p["id"])
    _generate_and_confirm_prd(client, p["id"])
    r = client.post(f"/api/v1/projects/{p['id']}/tasks")
    assert r.status_code == 202
    asyncio.run(task_worker.process_task(r.json()["id"]))

    tasks = client.get(f"/api/v1/projects/{p['id']}/tasks").json()
    assert len(tasks) == 5
    assert tasks[0]["priority"] == "P0"
    assert tasks[0]["module"] in ("前端", "后端", "AI", "数据", "集成", "测试")
    # #8 悬空依赖被过滤
    acceptance = next(t for t in tasks if t["title"] == "全链路验收")
    assert acceptance["dependencies"] == ["需求澄清生成"]


def test_update_and_delete_task(client):
    """#5 编辑/删除单个研发任务。"""
    p = _create_project(client)
    _setup_positioning(client, p["id"])
    _generate_and_confirm_prd(client, p["id"])
    asyncio.run(task_worker.process_task(client.post(f"/api/v1/projects/{p['id']}/tasks").json()["id"]))
    tasks = client.get(f"/api/v1/projects/{p['id']}/tasks").json()
    t0 = tasks[0]
    # PATCH 编辑标题
    r = client.patch(f"/api/v1/projects/{p['id']}/tasks/{t0['id']}", json={"title": "改后的标题"})
    assert r.status_code == 200
    assert r.json()["title"] == "改后的标题"
    # 非法 priority 拦截
    r = client.patch(f"/api/v1/projects/{p['id']}/tasks/{t0['id']}", json={"priority": "P9"})
    assert r.status_code == 422
    # DELETE
    r = client.delete(f"/api/v1/projects/{p['id']}/tasks/{t0['id']}")
    assert r.status_code == 200
    assert r.json() == {"deleted": t0["id"]}
    assert len(client.get(f"/api/v1/projects/{p['id']}/tasks").json()) == 4


def test_confirm_tasks_requires_p0(client):
    """#7 确认任务前必须存在 P0 任务。"""
    p = _create_project(client)
    _setup_positioning(client, p["id"])
    _generate_and_confirm_prd(client, p["id"])
    asyncio.run(task_worker.process_task(client.post(f"/api/v1/projects/{p['id']}/tasks").json()["id"]))
    tasks = client.get(f"/api/v1/projects/{p['id']}/tasks").json()
    for t in tasks:
        client.patch(f"/api/v1/projects/{p['id']}/tasks/{t['id']}", json={"priority": "P2"})
    r = client.put(f"/api/v1/projects/{p['id']}/tasks")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_INPUT"


def test_tasks_confirm_moves_to_package(client):
    p = _create_project(client)
    _setup_positioning(client, p["id"])
    _generate_and_confirm_prd(client, p["id"])
    asyncio.run(task_worker.process_task(client.post(f"/api/v1/projects/{p['id']}/tasks").json()["id"]))
    r = client.put(f"/api/v1/projects/{p['id']}/tasks")
    assert r.json()["current_stage"] == "package"
