from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.core.llm import LLMError
from app.services import digital_human, jimeng, video_worker


@pytest.mark.asyncio
@pytest.mark.parametrize("method,expected_calls", [("submit", 1), ("result", 4)])
async def test_only_read_queries_retry(monkeypatch, method, expected_calls):
    call = Mock(side_effect=Exception("Connection aborted secret-value"))
    monkeypatch.setattr(jimeng, "_service", lambda: SimpleNamespace(cv_submit_task=call, cv_get_result=call))
    monkeypatch.setattr(jimeng.asyncio, "sleep", AsyncMock())
    with pytest.raises(LLMError) as error:
        await jimeng._call_api(method, {})
    assert call.call_count == expected_calls
    assert error.value.code == "NETWORK"
    assert "secret-value" not in str(error.value)


def test_sdk_uses_https_and_bounded_timeouts(monkeypatch):
    service = Mock()
    monkeypatch.setattr(jimeng, "VisualService", lambda: service)
    monkeypatch.setattr(jimeng.settings, "jimeng_ak", "test-ak")
    monkeypatch.setattr(jimeng.settings, "jimeng_sk", "test-sk")
    jimeng._service()
    service.set_scheme.assert_called_once_with("https")
    service.set_connection_timeout.assert_called_once_with(10)
    service.set_socket_timeout.assert_called_once_with(60)


@pytest.mark.asyncio
async def test_missing_credentials_fail_before_upload(monkeypatch):
    monkeypatch.setattr(jimeng.settings, "jimeng_ak", "")
    upload = AsyncMock()
    monkeypatch.setattr(digital_human, "upload_file", upload)
    with pytest.raises(LLMError, match="凭据"):
        await jimeng.generate_talking_video("unused", "unused", "test")
    upload.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,code", [([], "PARSE_ERROR"), ({"code": 403, "message": "secret-value"}, "MODEL_ERROR")])
async def test_upstream_errors_are_validated_and_sanitized(monkeypatch, payload, code):
    call = Mock(return_value=payload)
    monkeypatch.setattr(jimeng, "_service", lambda: SimpleNamespace(cv_get_result=call))
    with pytest.raises(LLMError) as error:
        await jimeng._call_api("result", {})
    assert error.value.code == code
    assert "secret-value" not in str(error.value)
    assert call.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [{}, {"data": None}, {"data": {"task_id": ""}}])
async def test_submit_requires_task_id(monkeypatch, data):
    monkeypatch.setattr(jimeng, "_call_api", AsyncMock(return_value=data))
    with pytest.raises(LLMError, match="任务编号"):
        await jimeng.submit_task("unused", "unused")


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [None, {"status": "done"}, {"status": "expired"}, {"status": "failed", "message": "secret-value"}])
async def test_poll_rejects_invalid_results(monkeypatch, data):
    monkeypatch.setattr(jimeng, "_call_api", AsyncMock(return_value={"data": data}))
    monkeypatch.setattr(jimeng.asyncio, "sleep", AsyncMock())
    with pytest.raises(LLMError) as error:
        await jimeng.get_result("test", timeout=5)
    assert "secret-value" not in str(error.value)


@pytest.mark.asyncio
async def test_poll_returns_completed_url(monkeypatch):
    monkeypatch.setattr(jimeng, "_call_api", AsyncMock(side_effect=[
        {"data": {"status": "generating"}},
        {"data": {"status": "done", "video_url": "https://example.com/test.mp4"}},
    ]))
    monkeypatch.setattr(jimeng.asyncio, "sleep", AsyncMock())
    assert await jimeng.get_result("test", timeout=10) == "https://example.com/test.mp4"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,code", [(httpx.ReadTimeout(""), "TIMEOUT"), (httpx.ConnectError("secret-value"), "NETWORK")])
async def test_empty_http_errors_get_safe_codes(monkeypatch, failure, code):
    monkeypatch.setattr(httpx.AsyncClient, "request", AsyncMock(side_effect=failure))
    with pytest.raises(LLMError) as error:
        await digital_human._request("GET", "https://example.com")
    assert error.value.code == code
    assert str(error.value)
    assert "secret-value" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [(401, "UNAUTHORIZED"), (403, "UNAUTHORIZED"), (500, "FETCH_ERROR")])
async def test_http_status_checked_before_body(monkeypatch, status, code):
    monkeypatch.setattr(httpx.AsyncClient, "request", AsyncMock(return_value=httpx.Response(status, text="secret-value")))
    with pytest.raises(LLMError) as error:
        await digital_human._request("GET", "https://example.com")
    assert error.value.code == code
    assert "secret-value" not in str(error.value)


@pytest.mark.parametrize("response", [httpx.Response(200, text="secret-value"), httpx.Response(200, json=[])])
def test_file_service_validates_json(response):
    with pytest.raises(LLMError):
        digital_human._json(response)


def test_file_service_validates_required_fields():
    with pytest.raises(LLMError):
        digital_human._value({"data": {"uploaded_files": []}}, "data", "uploaded_files", 0, "file_id")


@pytest.mark.asyncio
async def test_worker_does_not_switch_provider_or_persist_secrets(monkeypatch, tmp_path):
    task = SimpleNamespace(status="queued", script_id="script", avatar_profile_id="profile")
    script = SimpleNamespace(content="test", topic_id="topic", platform="test", source_urls=[])
    profile = SimpleNamespace(avatar_asset_id=None)
    db = Mock()
    db.get.side_effect = [task, script, profile, None]
    monkeypatch.setattr(video_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(video_worker, "_photo_path", lambda _: "unused")
    monkeypatch.setattr(video_worker.settings, "dh_enabled", True)
    monkeypatch.setattr(video_worker.settings, "jimeng_enabled", True)
    monkeypatch.setattr(video_worker.settings, "jimeng_ak", "")
    monkeypatch.setattr(video_worker.tts, "synthesize", AsyncMock(return_value="test.mp3"))
    monkeypatch.setattr(video_worker.video_svc, "audio_duration", lambda _: 3)
    monkeypatch.setattr(video_worker.video_svc, "VIDEO_DIR", tmp_path)
    monkeypatch.setattr(video_worker.video_svc, "compose_video", lambda *_: "test.mp4")
    monkeypatch.setattr(video_worker.video_svc, "make_cover", lambda *_: "test.png")
    monkeypatch.setattr(video_worker.video_svc, "build_package", lambda *_: "test.zip")
    monkeypatch.setattr(video_worker.engine, "_client", lambda: None)
    monkeypatch.setattr(video_worker.packaging, "generate_packaging", AsyncMock(return_value=SimpleNamespace(model_dump=lambda: {})))
    alternate = AsyncMock()
    monkeypatch.setattr(digital_human, "generate_talking_video", alternate)
    await video_worker._process_video("test")
    alternate.assert_not_called()
    assert task.status == "success"
    assert "无口型" in task.error_message
    assert "NO_API_KEY" in task.error_message
    assert "secret-value" not in video_worker._safe_error(LLMError("MODEL_ERROR", "secret-value"))
    assert "secret-value" not in video_worker._safe_error(Exception("secret-value"))
    db.commit.assert_called()
