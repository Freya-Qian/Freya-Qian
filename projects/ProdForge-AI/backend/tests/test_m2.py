"""M2 竞品证据与定位测试。"""
from __future__ import annotations

import asyncio

from app.services import task_worker


def _create_project(client):
    return client.post("/api/v1/projects", json={"name": "番茄钟", "idea": "做一个番茄钟", "goal_type": "real"}).json()


def _setup_brief(client, project_id):
    """生成问题→回答→生成摘要→确认摘要。"""
    task_id = client.post(f"/api/v1/projects/{project_id}/clarify/questions").json()["id"]
    asyncio.run(task_worker.process_task(task_id))
    qs = client.get(f"/api/v1/projects/{project_id}/clarify/questions").json()
    client.post(f"/api/v1/projects/{project_id}/clarify/answers",
                json={"answers": [{"question_id": q["id"], "answer": "回答"} for q in qs]})
    task_id = client.post(f"/api/v1/projects/{project_id}/brief").json()["id"]
    asyncio.run(task_worker.process_task(task_id))
    client.put(f"/api/v1/projects/{project_id}/brief", json={"confirm": True})


def _add_competitor(client, project_id, name="Forest", url="https://forestapp.cc"):
    return client.post(f"/api/v1/projects/{project_id}/competitors",
                       json={"name": name, "url": url}).json()


def _add_competitor_with_evidence(client, project_id, name="Forest"):
    """添加竞品 + 2 张证据卡（ref_key E1/E2），供定位生成使用。"""
    comp = _add_competitor(client, project_id, name)
    for claim in ("结论1", "结论2"):
        client.post(f"/api/v1/projects/{project_id}/competitors/{comp['id']}/evidences",
                    json={"source_url": "https://forestapp.cc", "structured_claim": claim})
    return comp


# ── 竞品与证据卡 ──

def test_no_auto_seed(client):
    """新项目竞品为空（不硬编码任何竞品）。"""
    p = _create_project(client)
    assert client.get(f"/api/v1/projects/{p['id']}/competitors").json() == []


def test_add_competitor(client):
    p = _create_project(client)
    r = client.post(f"/api/v1/projects/{p['id']}/competitors",
                    json={"name": "Forest", "url": "https://forestapp.cc"})
    assert r.status_code == 201
    assert r.json()["name"] == "Forest"
    assert len(client.get(f"/api/v1/projects/{p['id']}/competitors").json()) == 1


def test_competitor_limit(client):
    """最多 3 个竞品，第 4 个被拦截。"""
    p = _create_project(client)
    for i in range(3):
        r = client.post(f"/api/v1/projects/{p['id']}/competitors",
                        json={"name": f"竞品{i}", "url": ""})
        assert r.status_code == 201
    r = client.post(f"/api/v1/projects/{p['id']}/competitors",
                    json={"name": "竞品4", "url": ""})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_add_evidence_validates_source_url(client):
    p = _create_project(client)
    comp = _add_competitor(client, p["id"])
    r = client.post(f"/api/v1/projects/{p['id']}/competitors/{comp['id']}/evidences",
                    json={"source_url": "not-a-url", "structured_claim": "x"})
    assert r.status_code == 422


def test_add_evidence_and_delete(client):
    p = _create_project(client)
    comp = _add_competitor(client, p["id"])
    r = client.post(f"/api/v1/projects/{p['id']}/competitors/{comp['id']}/evidences",
                    json={"source_url": "https://example.com/doc", "structured_claim": "某事实"})
    assert r.status_code == 201
    ev_id = r.json()["id"]
    assert client.delete(f"/api/v1/projects/{p['id']}/competitors/{comp['id']}/evidences/{ev_id}").status_code == 204
    assert client.get(f"/api/v1/projects/{p['id']}/competitors/{comp['id']}/evidences").json() == []


def test_evidence_keys_are_unique_across_competitors_and_deletion(client):
    p = _create_project(client)
    first = _add_competitor(client, p["id"], "Forest")
    second = _add_competitor(client, p["id"], "Focus To-Do")

    def add(comp):
        response = client.post(
            f"/api/v1/projects/{p['id']}/competitors/{comp['id']}/evidences",
            json={"source_url": "https://example.com", "structured_claim": "可核查结论"},
        )
        assert response.status_code == 201
        return response.json()

    first_ev = add(first)
    second_ev = add(second)
    assert [first_ev["ref_key"], second_ev["ref_key"]] == ["E1", "E2"]
    assert client.delete(
        f"/api/v1/projects/{p['id']}/competitors/{first['id']}/evidences/{first_ev['id']}"
    ).status_code == 204
    assert add(first)["ref_key"] == "E3"


# ── 定位生成 ──

def test_positioning_requires_brief(client):
    p = _create_project(client)
    r = client.post(f"/api/v1/projects/{p['id']}/positioning")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NOT_READY"


def test_positioning_requires_confirmed_brief(client):
    p = _create_project(client)
    task_id = client.post(f"/api/v1/projects/{p['id']}/clarify/questions").json()["id"]
    asyncio.run(task_worker.process_task(task_id))
    qs = client.get(f"/api/v1/projects/{p['id']}/clarify/questions").json()
    client.post(f"/api/v1/projects/{p['id']}/clarify/answers",
                json={"answers": [{"question_id": q["id"], "answer": "回答"} for q in qs]})
    asyncio.run(task_worker.process_task(client.post(f"/api/v1/projects/{p['id']}/brief").json()["id"]))
    r = client.post(f"/api/v1/projects/{p['id']}/positioning")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NOT_READY"


def test_positioning_requires_competitor(client):
    p = _create_project(client)
    _setup_brief(client, p["id"])
    r = client.post(f"/api/v1/projects/{p['id']}/positioning")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NOT_READY"


def test_positioning_generate_and_get(client):
    p = _create_project(client)
    _setup_brief(client, p["id"])
    _add_competitor_with_evidence(client, p["id"])
    r = client.post(f"/api/v1/projects/{p['id']}/positioning")
    assert r.status_code == 202
    asyncio.run(task_worker.process_task(r.json()["id"]))
    pos = client.get(f"/api/v1/projects/{p['id']}/positioning").json()
    assert pos["one_liner"] == "Web 端 AI 产品孵化工作台"
    assert len(pos["differentiators"]) == 2
    assert pos["evidence_refs"] == ["E1", "E2"]
    # 多竞品对比表结构
    assert pos["comparison"][0]["dimension"] == "定位"
    assert "Forest" in pos["comparison"][0]["competitors"]


def test_positioning_confirm_moves_to_prd(client):
    p = _create_project(client)
    _setup_brief(client, p["id"])
    _add_competitor_with_evidence(client, p["id"])
    asyncio.run(task_worker.process_task(client.post(f"/api/v1/projects/{p['id']}/positioning").json()["id"]))
    r = client.put(f"/api/v1/projects/{p['id']}/positioning", json={"one_liner": "改", "confirm": True})
    assert r.json()["status"] == "confirmed"
    assert client.get(f"/api/v1/projects/{p['id']}").json()["current_stage"] == "prd"


def test_evidence_used_in_marked(client):
    p = _create_project(client)
    _setup_brief(client, p["id"])
    comp = _add_competitor_with_evidence(client, p["id"])
    asyncio.run(task_worker.process_task(client.post(f"/api/v1/projects/{p['id']}/positioning").json()["id"]))
    evs = client.get(f"/api/v1/projects/{p['id']}/competitors/{comp['id']}/evidences").json()
    by_key = {e["ref_key"]: e for e in evs}
    assert "定位" in by_key["E1"]["used_in"]


# ── 评审修复项回归 ──

def test_differentiator_without_evidence_marked():
    from app.services.positioning import _clean_differentiators
    diffs = _clean_differentiators(
        [{"point": "某差异", "evidence_refs": []}, {"point": "某差异2", "evidence_refs": ["不存在"]}],
        {"E1"},
    )
    assert diffs[0]["point"] == "某差异（待补证：无证据引用）"
    assert diffs[1]["point"] == "某差异2（待补证：无证据引用）"


def test_update_evidence(client):
    p = _create_project(client)
    comp = _add_competitor_with_evidence(client, p["id"])
    ev = client.get(f"/api/v1/projects/{p['id']}/competitors/{comp['id']}/evidences").json()[0]
    r = client.patch(f"/api/v1/projects/{p['id']}/competitors/{comp['id']}/evidences/{ev['id']}",
                     json={"structured_claim": "改", "confidence": "合理推断"})
    assert r.json()["structured_claim"] == "改"
    assert r.json()["confidence"] == "合理推断"


def test_delete_referenced_evidence_blocked(client):
    p = _create_project(client)
    _setup_brief(client, p["id"])
    comp = _add_competitor_with_evidence(client, p["id"])
    asyncio.run(task_worker.process_task(client.post(f"/api/v1/projects/{p['id']}/positioning").json()["id"]))
    evs = client.get(f"/api/v1/projects/{p['id']}/competitors/{comp['id']}/evidences").json()
    e1 = next(e for e in evs if e["ref_key"] == "E1")
    r = client.delete(f"/api/v1/projects/{p['id']}/competitors/{comp['id']}/evidences/{e1['id']}")
    assert r.status_code == 409


# ── 贴网址抓取 ──

def test_fetch_evidence(client):
    p = _create_project(client)
    comp = _add_competitor(client, p["id"])
    r = client.post(f"/api/v1/projects/{p['id']}/competitors/{comp['id']}/evidences/fetch",
                    json={"url": "https://forestapp.cc"})
    assert r.status_code == 202
    asyncio.run(task_worker.process_task(r.json()["id"]))
    evs = client.get(f"/api/v1/projects/{p['id']}/competitors/{comp['id']}/evidences").json()
    assert len(evs) == 1
    assert evs[0]["source_url"] == "https://forestapp.cc"
    assert evs[0]["confidence"] == "合理推断"


def test_fetch_evidence_invalid_url(client):
    p = _create_project(client)
    comp = _add_competitor(client, p["id"])
    r = client.post(f"/api/v1/projects/{p['id']}/competitors/{comp['id']}/evidences/fetch",
                    json={"url": "not-a-url"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_URL"
