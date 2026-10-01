"""项目创建/列表/详情与冷启动示例接口测试。"""
from __future__ import annotations


def test_samples(client):
    r = client.get("/api/v1/samples")
    assert r.status_code == 200
    data = r.json()
    assert len(data["samples"]) == 3
    assert len(data["goal_types"]) == 4


def test_create_project(client):
    r = client.post("/api/v1/projects", json={"name": "番茄钟", "idea": "做一个番茄钟", "goal_type": "real"})
    assert r.status_code == 201
    p = r.json()
    assert p["name"] == "番茄钟"
    assert p["current_stage"] == "clarify"
    assert p["status"] == "active"
    assert p["id"]


def test_create_project_invalid_goal_type(client):
    r = client.post("/api/v1/projects", json={"name": "x", "idea": "y", "goal_type": "bad"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_INPUT"


def test_create_project_empty_name(client):
    r = client.post("/api/v1/projects", json={"name": "", "idea": "y", "goal_type": "real"})
    assert r.status_code == 422


def test_list_and_get_project(client):
    r = client.post("/api/v1/projects", json={"name": "番茄钟", "idea": "做一个番茄钟", "goal_type": "real"})
    pid = r.json()["id"]

    r = client.get("/api/v1/projects")
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = client.get(f"/api/v1/projects/{pid}")
    assert r.status_code == 200
    assert r.json()["name"] == "番茄钟"


def test_get_project_not_found(client):
    r = client.get("/api/v1/projects/not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
