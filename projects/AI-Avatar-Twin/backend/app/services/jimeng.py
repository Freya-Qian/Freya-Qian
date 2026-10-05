"""即梦（OmniHuman）数字人口型驱动视频：火山引擎智能视觉 CV API（用官方 SDK 签名）。"""
from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path

from volcengine.visual.VisualService import VisualService

from app.config import VIDEO_DIR, settings
from app.core.llm import LLMError
from app.services import digital_human  # 复用文件上传/下载/切段/拼接
from app.services.video import audio_duration

REQ_KEY = "jimeng_realman_avatar_picture_omni_v15"


def _service() -> VisualService:
    if not settings.jimeng_ak or not settings.jimeng_sk:
        raise LLMError("NO_API_KEY", "即梦凭据未配置")
    vs = VisualService()
    vs.set_scheme("https")
    vs.set_connection_timeout(10)
    vs.set_socket_timeout(60)
    vs.set_ak(settings.jimeng_ak)
    vs.set_sk(settings.jimeng_sk)
    return vs


async def _call_api(method: str, form: dict, retries: int = 3) -> dict:
    """只对只读查询重试；提交结果不明时禁止自动重复付费。"""
    if method not in ("submit", "result"):
        raise ValueError("unsupported method")
    if method == "submit":
        retries = 0
    for attempt in range(retries + 1):
        try:
            def _do():
                vs = _service()
                if method == "submit":
                    return vs.cv_submit_task(form)
                return vs.cv_get_result(form)
            data = await asyncio.to_thread(_do)
            if not isinstance(data, dict):
                raise LLMError("PARSE_ERROR", "即梦返回格式异常")
            if data.get("code") != 10000:
                raise LLMError("MODEL_ERROR", "即梦拒绝请求，请核对服务权限、额度与参数")
            return data
        except LLMError:
            raise
        except Exception as e:
            msg = str(e)
            if attempt < retries and ("Connection" in msg or "RemoteDisconnected" in msg or "aborted" in msg or "timed out" in msg):
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if method == "submit":
                raise LLMError("NETWORK", "即梦提交结果未确认，请先在服务商控制台核对任务，勿直接重试") from None
            raise LLMError("NETWORK", "即梦任务查询连接失败") from None
    raise LLMError("NETWORK", "即梦接口调用失败")


async def submit_task(image_url: str, audio_url: str) -> str:
    data = await _call_api("submit", {
        "req_key": REQ_KEY,
        "image_url": image_url,
        "mask_url": [],
        "audio_url": audio_url,
        "prompt": "",
    })
    d = data.get("data")
    if not isinstance(d, dict) or not isinstance(d.get("task_id"), str) or not d["task_id"]:
        raise LLMError("PARSE_ERROR", "即梦未返回任务编号，请先在服务商控制台核对任务，勿直接重试")
    return d["task_id"]


async def get_result(task_id: str, timeout: int = 3600) -> str:
    """轮询任务结果。查询本身失败（网络抖动/限流/格式异常）不视为任务失败，继续轮询；
    仅当任务明确 done / failed / 消失，或超过 deadline 时才终止。"""
    deadline = time.monotonic() + timeout
    while True:
        if time.monotonic() > deadline:
            raise LLMError("TIMEOUT", "即梦生成超时")
        await asyncio.sleep(5)
        try:
            data = await _call_api("result", {"req_key": REQ_KEY, "task_id": task_id})
        except LLMError:
            # 查询失败不代表任务失败，继续轮询到 deadline
            continue
        d = data.get("data", {})
        if not isinstance(d, dict):
            continue
        status = d.get("status")
        if status == "done":
            vurl = d.get("video_url")
            if not isinstance(vurl, str) or not vurl.startswith("https://"):
                raise LLMError("PARSE_ERROR", "即梦未返回有效视频地址")
            return vurl
        if status in ("failed", "error"):
            raise LLMError("MODEL_ERROR", "即梦生成失败，请在服务商控制台查看任务")
        if status in (None, "not_found", "expired"):
            raise LLMError("MODEL_ERROR", "即梦任务不存在、已过期或状态异常")


async def generate_talking_video(photo_path: str, audio_path: str, out_name: str) -> str:
    """照片 + 配音 → 即梦数字人口型视频（复用阿里云文件上传拿公网 URL）。"""
    if not settings.jimeng_ak or not settings.jimeng_sk:
        raise LLMError("NO_API_KEY", "即梦凭据未配置")
    image_url = await digital_human.upload_file(photo_path)
    dur = audio_duration(audio_path)
    segments = [Path(audio_path)] if dur <= settings.dh_segment else digital_human._split_audio(audio_path, out_name)

    video_paths: list[Path] = []
    for i, seg in enumerate(segments):
        audio_url = await digital_human.upload_file(str(seg))
        task_id = await submit_task(image_url, audio_url)
        vurl = await get_result(task_id)
        seg_video = VIDEO_DIR / f"{out_name}_seg{i}.mp4"
        await digital_human._download(vurl, seg_video)
        video_paths.append(seg_video)

    if len(video_paths) == 1:
        final = VIDEO_DIR / f"{out_name}.mp4"
        try:
            subprocess.run(
                ["ffmpeg", "-i", str(video_paths[0]), "-c:v", "libx264", "-c:a", "aac",
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(final)],
                check=True, capture_output=True,
            )
            return str(final)
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            # ffmpeg 转码失败兜底：直接使用即梦返回的 mp4（本身可播放），不因此降级静态合成
            return str(video_paths[0])
    return digital_human._concat_videos(video_paths, out_name)
