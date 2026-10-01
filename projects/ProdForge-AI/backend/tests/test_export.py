"""M4 资料包导出测试。"""
from __future__ import annotations

import asyncio
import json

from app.services import task_worker


def _create_project(client):
    return client.post("/api/v1/projects",
                       json={"name": "番茄钟", "idea": "做一个番茄钟", "goal_type": "real"}).json()


def _setup_full_project(client):
    """走完 澄清→摘要→竞品→定位→PRD→任务 全流程，返回 project_id。"""
    p = _create_project(client)
    pid = p["id"]
    asyncio.run(task_worker.process_task(
        client.post(f"/api/v1/projects/{pid}/clarify/questions").json()["id"]))
    qs = client.get(f"/api/v1/projects/{pid}/clarify/questions").json()
    client.post(f"/api/v1/projects/{pid}/clarify/answers",
                json={"answers": [{"question_id": q["id"], "answer": "回答"} for q in qs]})
    asyncio.run(task_worker.process_task(
        client.post(f"/api/v1/projects/{pid}/brief").json()["id"]))
    client.put(f"/api/v1/projects/{pid}/brief", json={"confirm": True})
    comp = client.post(f"/api/v1/projects/{pid}/competitors",
                       json={"name": "Forest", "url": "https://forestapp.cc"}).json()
    client.post(f"/api/v1/projects/{pid}/competitors/{comp['id']}/evidences",
                json={"source_url": "https://forestapp.cc", "structured_claim": "结论1"})
    asyncio.run(task_worker.process_task(
        client.post(f"/api/v1/projects/{pid}/positioning").json()["id"]))
    client.put(f"/api/v1/projects/{pid}/positioning", json={"confirm": True})
    asyncio.run(task_worker.process_task(
        client.post(f"/api/v1/projects/{pid}/prd").json()["id"]))
    client.put(f"/api/v1/projects/{pid}/prd", json={"confirm": True})
    asyncio.run(task_worker.process_task(
        client.post(f"/api/v1/projects/{pid}/tasks").json()["id"]))
    client.put(f"/api/v1/projects/{pid}/tasks")
    return pid


def test_export_markdown(client):
    """Markdown 导出包含资料包全部章节。"""
    pid = _setup_full_project(client)
    r = client.post(f"/api/v1/projects/{pid}/export", json={"channel": "markdown"})
    assert r.status_code == 200
    data = r.json()
    assert data["channel"] == "markdown"
    assert "项目资料包" in data["title"]
    content = data["content"]
    for sec in ["项目简介", "需求澄清摘要", "竞品证据与分析", "产品定位与差异点",
                "PRD", "研发任务拆解", "待确认问题", "迭代记录",
                "证据来源与引用说明", "交接说明"]:
        assert sec in content, f"缺少章节：{sec}"
    assert "E1" in content  # 证据引用说明含 ref_key


def test_export_invalid_channel(client):
    p = _create_project(client)
    r = client.post(f"/api/v1/projects/{p['id']}/export", json={"channel": "invalid"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_INPUT"


def test_export_github_issue(client):
    """GitHub issue 通道：标题带 [项目资料包]。"""
    pid = _setup_full_project(client)
    r = client.post(f"/api/v1/projects/{pid}/export", json={"channel": "github_issue"})
    assert r.status_code == 200
    assert r.json()["title"].startswith("[项目资料包]")


def test_export_writes_export_table(client):
    """导出写 Export 表（channel/status 正确）。"""
    from app import models

    pid = _setup_full_project(client)
    r = client.post(f"/api/v1/projects/{pid}/export", json={"channel": "markdown"})
    assert r.status_code == 200
    db = task_worker.SessionLocal()
    exps = db.query(models.Export).filter(models.Export.project_id == pid).all()
    db.close()
    assert len(exps) == 1
    assert exps[0].channel == "markdown"
    assert exps[0].status == "success"


def test_export_records_event(client, tmp_path):
    """导出触发 exported 埋点。"""
    pid = _setup_full_project(client)
    client.post(f"/api/v1/projects/{pid}/export", json={"channel": "markdown"})
    events_file = tmp_path / "events_test.jsonl"
    events = [json.loads(l) for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert any(e["event"] == "exported" and e["project_id"] == pid for e in events)
