"""M2 API 测试：账户 / 数据隔离 / 项目 / Profile / 信息源 / 全链路。"""
import json
import re

import pytest


def _register(client, phone="13800138000"):
    r = client.post("/api/v1/auth/code", json={"phone": phone})
    assert r.status_code == 200, r.text
    code = r.json()["dev_code"]
    r = client.post("/api/v1/auth/verify", json={"phone": phone, "code": code})
    assert r.status_code == 200, r.text
    return r.json()


def _h(token):
    return {"Authorization": "Bearer " + token}


def _create_project(client, token, name="项目A"):
    r = client.post("/api/v1/projects", json={"name": name}, headers=_h(token))
    assert r.status_code == 200, r.text
    return r.json()


def _create_profile(client, token, pid):
    r = client.post(f"/api/v1/projects/{pid}/profiles", json={
        "name": "数字人1", "style_tags": ["专业"], "language": "zh",
        "topic_preferences": ["AI 工具"], "catchphrases": ["关注我"],
        "banned_phrases": [], "avatar_type": "template", "voice_type": "default_tts",
        "video_ratio": "9:16", "platform_preferences": ["douyin"],
    }, headers=_h(token))
    assert r.status_code == 200, r.text
    return r.json()


def _create_url_source(client, token, pid, url="https://example.com"):
    r = client.post("/api/v1/sources", json={"project_id": pid, "source_type": "url", "url": url}, headers=_h(token))
    assert r.status_code == 200, r.text
    return r.json()


def _sse_script(client, token, topic_id):
    r = client.post(f"/api/v1/topics/{topic_id}/scripts", headers=_h(token))
    assert r.status_code == 200, r.text
    body = r.text
    assert '"script"' in body
    m = re.search(r'data: (\{.*"script".*\})\n', body)
    assert m, body
    return json.loads(m.group(1))["script"]


def test_unauthorized_rejected(client):
    r = client.get("/api/v1/projects")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("template_id", [1, 2, 3])
def test_profile_template_creation_persists(client, template_id):
    token = _register(client)["token"]
    project = _create_project(client, token)
    url = f"/api/v1/projects/{project['id']}/profiles"
    response = client.post(url, json={"name": "Avatar", "template_id": template_id}, headers=_h(token))
    assert response.status_code == 200, response.text
    profile = response.json()
    assert profile["template_id"] == template_id
    # A separate request reads the committed row through a fresh DB session.
    listed = client.get(url, headers=_h(token))
    assert listed.status_code == 200
    assert listed.json() == [profile]


def test_profile_template_defaults_to_one(client):
    token = _register(client)["token"]
    project = _create_project(client, token)
    profile = _create_profile(client, token, project["id"])
    assert profile["template_id"] == 1
    response = client.get(f"/api/v1/projects/{project['id']}/profiles", headers=_h(token))
    assert response.json() == [profile]


@pytest.mark.parametrize("template_id", [0, -1, 4, 999, "2", "invalid", 1.0, 1.5, True, False, [], {}])
@pytest.mark.parametrize("operation", ["create", "update"])
def test_profile_invalid_template_rejected(client, template_id, operation):
    token = _register(client)["token"]
    project = _create_project(client, token)
    url = f"/api/v1/projects/{project['id']}/profiles"
    if operation == "create":
        expected = []
        response = client.post(url, json={"name": "Avatar", "template_id": template_id}, headers=_h(token))
    else:
        profile = _create_profile(client, token, project["id"])
        expected = [profile]
        response = client.patch(f"/api/v1/profiles/{profile['id']}", json={"template_id": template_id}, headers=_h(token))
    assert response.status_code == 422, response.text
    assert client.get(url, headers=_h(token)).json() == expected


def test_profile_null_template_creation_rejected(client):
    token = _register(client)["token"]
    project = _create_project(client, token)
    url = f"/api/v1/projects/{project['id']}/profiles"
    response = client.post(url, json={"name": "Avatar", "template_id": None}, headers=_h(token))
    assert response.status_code == 422
    assert client.get(url, headers=_h(token)).json() == []


@pytest.mark.parametrize("template_id", [1, 2, 3])
def test_profile_template_update_persists(client, template_id):
    token = _register(client)["token"]
    project = _create_project(client, token)
    profile = _create_profile(client, token, project["id"])
    response = client.patch(f"/api/v1/profiles/{profile['id']}", json={"template_id": template_id}, headers=_h(token))
    assert response.status_code == 200, response.text
    assert response.json()["template_id"] == template_id
    listed = client.get(f"/api/v1/projects/{project['id']}/profiles", headers=_h(token))
    assert listed.json() == [response.json()]


def test_register_and_me(client):
    auth = _register(client)
    assert auth["token"]
    r = client.get("/api/v1/auth/me", headers=_h(auth["token"]))
    assert r.status_code == 200
    assert r.json()["phone"] == "13800138000"


def test_bad_code_rejected(client):
    client.post("/api/v1/auth/code", json={"phone": "13800138000"})
    r = client.post("/api/v1/auth/verify", json={"phone": "13800138000", "code": "000000"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_INPUT"


def test_full_flow(client):
    auth = _register(client)
    token, h = auth["token"], _h(auth["token"])

    proj = _create_project(client, token)
    _create_profile(client, token, proj["id"])
    src = _create_url_source(client, token, proj["id"])

    # 抓取
    r = client.post(f"/api/v1/sources/{src['id']}/fetch", headers=h)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1

    # 摘要
    r = client.post(f"/api/v1/items/{items[0]['id']}/summarize", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "summarized"

    # 选题
    r = client.post(f"/api/v1/items/{items[0]['id']}/topics", headers=h)
    assert r.status_code == 200
    topics = r.json()
    assert len(topics) == 3

    # 脚本
    script = _sse_script(client, token, topics[0]["id"])
    sid = script["id"]
    assert script["version"] == 1

    # 脚本选择器只能看到当前项目的脚本
    other_proj = _create_project(client, token, "项目B")
    assert [s["id"] for s in client.get(f"/api/v1/scripts?project_id={proj['id']}", headers=h).json()] == [sid]
    assert client.get(f"/api/v1/scripts?project_id={other_proj['id']}", headers=h).json() == []

    # 版本/回退/导出
    r = client.patch(f"/api/v1/scripts/{sid}", json={"content": "改过的"}, headers=h)
    assert r.json()["version"] == 2
    r = client.post(f"/api/v1/scripts/{sid}/revert", json={"version": 1}, headers=h)
    assert r.json()["version"] == 1
    r = client.get(f"/api/v1/scripts/{sid}/export?format=md", headers=h)
    assert "来源" in r.json()["content"]


def test_rss_fetch(client):
    auth = _register(client)
    token, h = auth["token"], _h(auth["token"])
    proj = _create_project(client, token)
    r = client.post("/api/v1/sources", json={"project_id": proj["id"], "source_type": "rss", "url": "https://example.com/feed.xml"}, headers=h)
    src = r.json()
    r = client.post(f"/api/v1/sources/{src['id']}/fetch", headers=h)
    assert r.status_code == 200
    assert len(r.json()) == 3  # FakeFeed 3 条


def test_manual_source(client):
    auth = _register(client)
    token, h = auth["token"], _h(auth["token"])
    proj = _create_project(client, token)
    r = client.post("/api/v1/sources", json={"project_id": proj["id"], "source_type": "manual", "content": "这是一段手动输入的 AI 资讯正文"}, headers=h)
    src = r.json()
    r = client.post(f"/api/v1/sources/{src['id']}/fetch", headers=h)
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_dedup(client):
    auth = _register(client)
    token, h = auth["token"], _h(auth["token"])
    proj = _create_project(client, token)
    src = _create_url_source(client, token, proj["id"])
    r1 = client.post(f"/api/v1/sources/{src['id']}/fetch", headers=h)
    r2 = client.post(f"/api/v1/sources/{src['id']}/fetch", headers=h)
    assert len(r1.json()) == 1
    assert len(r2.json()) == 0  # 去重


def test_data_isolation(client):
    a = _register(client, "13800138000")
    b = _register(client, "13900139000")
    ha, hb = _h(a["token"]), _h(b["token"])

    proj_a = _create_project(client, a["token"], "A的项目")
    _create_url_source(client, a["token"], proj_a["id"])

    # B 看不到 A 的项目/信息源/条目
    assert client.get("/api/v1/projects", headers=hb).json() == []
    assert client.get("/api/v1/sources", headers=hb).json() == []
    assert client.get("/api/v1/items", headers=hb).json() == []

    # B 无法访问 A 的项目
    r = client.patch(f"/api/v1/projects/{proj_a['id']}", json={"name": "x"}, headers=hb)
    assert r.status_code == 404


def test_logout_revokes_bearer_token(client):
    token = _register(client)["token"]
    headers = _h(token)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
