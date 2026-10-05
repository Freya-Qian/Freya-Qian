"""M3 测试：SRT 生成、图片校验、照片上传、视频任务创建。"""
import json
import re
from io import BytesIO

from PIL import Image

from app.api.routes import _check_image
from app.config import settings
from app.services import video_worker
from app.services.video import generate_srt


def _register(client, phone="13800138000"):
    client.post("/api/v1/auth/code", json={"phone": phone})
    code = client.post("/api/v1/auth/code", json={"phone": phone}).json()["dev_code"]
    r = client.post("/api/v1/auth/verify", json={"phone": phone, "code": code})
    return r.json()


def _h(token):
    return {"Authorization": "Bearer " + token}


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), "#69d8c6").save(buf, format="PNG")
    return buf.getvalue()


def _make_script(client):
    """跑通到脚本，返回 (token, h, script_id, proj_id)。"""
    auth = _register(client)
    token, h = auth["token"], _h(auth["token"])
    proj = client.post("/api/v1/projects", json={"name": "p"}, headers=h).json()
    src = client.post("/api/v1/sources", json={"project_id": proj["id"], "source_type": "url", "url": "https://example.com"}, headers=h).json()
    items = client.post(f"/api/v1/sources/{src['id']}/fetch", headers=h).json()
    client.post(f"/api/v1/items/{items[0]['id']}/summarize", headers=h)
    topics = client.post(f"/api/v1/items/{items[0]['id']}/topics", headers=h).json()
    r = client.post(f"/api/v1/topics/{topics[0]['id']}/scripts", headers=h)
    m = re.search(r'data: (\{.*"script".*\})\n', r.text)
    return token, h, json.loads(m.group(1))["script"]["id"], proj["id"]


# ---------- 纯函数 ----------


def test_generate_srt_has_entries():
    srt = generate_srt("第一句。第二句！第三句？", 10.0)
    assert srt.count("-->") == 3
    assert "00:00:" in srt


def test_generate_srt_empty():
    assert generate_srt("", 10.0) == ""


def test_check_image_png_ok():
    assert _check_image(b"\x89PNG\r\n\x1a\nxxxx", ".png") is True


def test_check_image_fake_rejected():
    assert _check_image(b"hello world", ".png") is False


# ---------- 照片上传 ----------


def test_photo_upload_invalid_type(client):
    auth = _register(client)
    token, h = auth["token"], _h(auth["token"])
    proj = client.post("/api/v1/projects", json={"name": "p"}, headers=h).json()
    prof = client.post(f"/api/v1/projects/{proj['id']}/profiles", json={"name": "x"}, headers=h).json()
    r = client.post(f"/api/v1/profiles/{prof['id']}/photo", headers=h,
                    data={"consent": "true"},
                    files={"file": ("fake.png", b"not-an-image", "image/png")})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_INPUT"


def test_photo_upload_no_consent_rejected(client):
    auth = _register(client)
    token, h = auth["token"], _h(auth["token"])
    proj = client.post("/api/v1/projects", json={"name": "p"}, headers=h).json()
    prof = client.post(f"/api/v1/projects/{proj['id']}/profiles", json={"name": "x"}, headers=h).json()
    r = client.post(f"/api/v1/profiles/{prof['id']}/photo", headers=h,
                    files={"file": ("ok.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_INPUT"


def test_photo_upload_valid_png(client):
    auth = _register(client)
    token, h = auth["token"], _h(auth["token"])
    proj = client.post("/api/v1/projects", json={"name": "p"}, headers=h).json()
    prof = client.post(f"/api/v1/projects/{proj['id']}/profiles", json={"name": "x"}, headers=h).json()
    r = client.post(f"/api/v1/profiles/{prof['id']}/photo", headers=h,
                    data={"consent": "true"},
                    files={"file": ("ok.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")})
    assert r.status_code == 200
    assert r.json()["avatar_type"] == "uploaded_self"


def test_delete_project_removes_profiles_and_sources(client):
    auth = _register(client)
    token, h = auth["token"], _h(auth["token"])
    proj = client.post("/api/v1/projects", json={"name": "p"}, headers=h).json()
    client.post(f"/api/v1/projects/{proj['id']}/profiles", json={"name": "x"}, headers=h)
    src = client.post("/api/v1/sources", json={"project_id": proj["id"], "source_type": "url", "url": "https://example.com/p"}, headers=h).json()
    assert client.delete(f"/api/v1/projects/{proj['id']}", headers=h).status_code == 200
    assert all(p["id"] != proj["id"] for p in client.get("/api/v1/projects", headers=h).json())
    assert client.get(f"/api/v1/projects/{proj['id']}/profiles", headers=h).json() == []
    assert all(s["id"] != src["id"] for s in client.get("/api/v1/sources", headers=h).json())


def test_avatar_preview_after_photo_upload_returns_image(client, monkeypatch):
    monkeypatch.setattr(settings, "stylize_api_key", "")
    auth = _register(client)
    token, h = auth["token"], _h(auth["token"])
    proj = client.post("/api/v1/projects", json={"name": "p"}, headers=h).json()
    prof = client.post(f"/api/v1/projects/{proj['id']}/profiles", json={"name": "x"}, headers=h).json()
    client.post(f"/api/v1/profiles/{prof['id']}/photo", headers=h,
                data={"consent": "true"},
                files={"file": ("ok.png", _png_bytes(), "image/png")})
    r = client.get(f"/api/v1/profiles/{prof['id']}/avatar-preview", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")
    assert len(r.content) > 100


# ---------- 视频任务 ----------


def test_create_video_queued(client, monkeypatch):
    monkeypatch.setattr(video_worker, "enqueue", lambda vid: None)
    token, h, script_id, proj_id = _make_script(client)
    prof = client.post(f"/api/v1/projects/{proj_id}/profiles", json={"name": "x"}, headers=h).json()
    client.post(f"/api/v1/profiles/{prof['id']}/photo", headers=h,
                data={"consent": "true"},
                files={"file": ("ok.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")})
    r = client.post(f"/api/v1/scripts/{script_id}/videos", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    vid = r.json()["id"]

    r = client.get(f"/api/v1/videos/{vid}", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


def test_create_video_uses_selected_profile(client, monkeypatch):
    monkeypatch.setattr(video_worker, "enqueue", lambda vid: None)
    token, h, script_id, proj_id = _make_script(client)
    client.post(f"/api/v1/projects/{proj_id}/profiles", json={"name": "default"}, headers=h)
    selected = client.post(f"/api/v1/projects/{proj_id}/profiles", json={"name": "selected"}, headers=h).json()
    r = client.post(
        f"/api/v1/scripts/{script_id}/videos",
        json={"avatar_profile_id": selected["id"]},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["avatar_profile_id"] == selected["id"]


def test_create_video_no_photo_rejected(client, monkeypatch):
    monkeypatch.setattr(video_worker, "enqueue", lambda vid: None)
    token, h, script_id, _ = _make_script(client)
    r = client.post(f"/api/v1/scripts/{script_id}/videos", headers=h)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_INPUT"


def test_video_404(client):
    auth = _register(client)
    r = client.get("/api/v1/videos/nonexistent", headers=_h(auth["token"]))
    assert r.status_code == 404
