"""M2 竞品自动推荐（方案 A：LLM 推荐）测试。"""
from __future__ import annotations

import asyncio
import json

from app.services import task_worker


def test_recommend_competitors(client):
    """推荐端点返回任务，完成后 result_json 含推荐竞品列表。"""
    p = client.post("/api/v1/projects",
                    json={"name": "番茄钟", "idea": "做一个番茄钟", "goal_type": "real"}).json()
    r = client.post(f"/api/v1/projects/{p['id']}/competitors/recommend")
    assert r.status_code == 202
    task_id = r.json()["id"]
    asyncio.run(task_worker.process_task(task_id))
    t = client.get(f"/api/v1/tasks/{task_id}").json()
    assert t["status"] == "success"
    recs = json.loads(t["result_json"])["competitors"]
    assert len(recs) == 2
    assert recs[0]["name"] == "Forest"
    assert recs[0]["url"].startswith("https://")


def test_recommend_blocked_when_full(client):
    """竞品已满（3 个）时推荐返回 409。"""
    p = client.post("/api/v1/projects",
                    json={"name": "番茄钟", "idea": "做一个番茄钟", "goal_type": "real"}).json()
    for i in range(3):
        client.post(f"/api/v1/projects/{p['id']}/competitors",
                    json={"name": f"竞品{i}", "url": "https://example.com"})
    r = client.post(f"/api/v1/projects/{p['id']}/competitors/recommend")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"
