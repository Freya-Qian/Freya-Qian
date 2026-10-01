"""S1 设置页模型配置端点测试（GET/PUT /settings/model）。"""
from __future__ import annotations


def test_get_model_settings_returns_tail4(client):
    """GET 返回 configured + Key 只回尾 4 位。"""
    r = client.get("/api/v1/settings/model")
    assert r.status_code == 200
    d = r.json()
    assert "configured" in d
    assert "model_api_key" in d
    assert len(d["model_api_key"]) <= 4  # 只回尾 4 位，绝不回传完整 Key


def test_update_model_settings_saves_and_hot_reload(client, monkeypatch, tmp_path):
    """PUT 保存后：GET 回显尾 4 位、settings 热更新、.env 已写入。"""
    from app import config

    original = {
        "key": config.settings.model_api_key,
        "name": config.settings.model_name,
        "base_url": config.settings.model_base_url,
    }
    # 重定向 .env 到临时目录，避免污染真实配置
    monkeypatch.setattr(config, "PROJECT_DIR", tmp_path)
    try:
        r = client.put("/api/v1/settings/model", json={
            "model_api_key": "sk-test-1234567890",
            "model_name": "qwen-plus",
            "model_base_url": "https://example.com/v1",
        })
        assert r.status_code == 200
        d = r.json()
        assert d["configured"] is True
        assert d["model_api_key"] == "7890"  # 尾 4 位
        # 热更新生效（无需重启）
        assert config.settings.model_api_key == "sk-test-1234567890"
        assert config.settings.model_name == "qwen-plus"
        assert config.settings.model_base_url == "https://example.com/v1"
        # .env 已写入，且 base_url 去掉末尾斜杠
        env_content = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "MODEL_API_KEY=sk-test-1234567890" in env_content
        assert "MODEL_NAME=qwen-plus" in env_content
        assert "MODEL_BASE_URL=https://example.com/v1" in env_content
    finally:
        config.settings.model_api_key = original["key"]
        config.settings.model_name = original["name"]
        config.settings.model_base_url = original["base_url"]


def test_update_model_settings_blank_key_422(client):
    """纯空格 Key 保存返回 422。"""
    r = client.put("/api/v1/settings/model", json={"model_api_key": "   "})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_INPUT"
