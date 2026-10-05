"""数字人口型驱动视频：万相-数字人（wan2.2-s2v），照片+音频→口型同步视频。"""
from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path

import httpx

from app.config import AUDIO_DIR, VIDEO_DIR, settings
from app.core.llm import LLMError
from app.services.video import audio_duration


def _headers() -> dict:
    if not settings.dh_api_key:
        raise LLMError("NO_API_KEY", "数字人文件服务凭据未配置")
    return {"Authorization": f"Bearer {settings.dh_api_key}"}


async def _request(method: str, url: str, *, timeout: int = 60, **kwargs) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, url, **kwargs)
    except httpx.TimeoutException:
        raise LLMError("TIMEOUT", "数字人文件或视频服务响应超时；提交结果需在控制台核对") from None
    except httpx.RequestError:
        raise LLMError("NETWORK", "数字人文件或视频服务连接失败") from None
    if response.status_code in (401, 403):
        raise LLMError("UNAUTHORIZED", "数字人文件或视频服务鉴权失败")
    if not response.is_success:
        raise LLMError("FETCH_ERROR", "数字人文件或视频服务请求失败")
    return response


def _json(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError:
        raise LLMError("PARSE_ERROR", "数字人服务返回格式异常") from None
    if not isinstance(data, dict):
        raise LLMError("PARSE_ERROR", "数字人服务返回格式异常")
    return data


def _value(data, *keys):
    try:
        for key in keys:
            data = data[key]
    except (KeyError, IndexError, TypeError):
        raise LLMError("PARSE_ERROR", "数字人服务返回缺少必要字段") from None
    if not isinstance(data, str) or not data:
        raise LLMError("PARSE_ERROR", "数字人服务返回字段无效")
    return data


async def upload_file(path: str, retries: int = 3) -> str:
    """上传本地文件到 DashScope，返回公网 URL（两步：上传拿 file_id → 查 url）。
    网络/超时/格式异常重试，避免偶发抖动导致整条视频降级。"""
    p = Path(path)
    with open(p, "rb") as f:
        content = f.read()
    last: LLMError | None = None
    for attempt in range(retries + 1):
        try:
            r = await _request(
                "POST", f"{settings.dh_base_url.rstrip('/')}/files",
                headers={**_headers(), "X-DashScope-OssResourceResolve": "enable"},
                files={"files": (p.name, content)},
            )
            fid = _value(_json(r), "data", "uploaded_files", 0, "file_id")
            r = await _request("GET", f"{settings.dh_base_url.rstrip('/')}/files/{fid}", headers=_headers())
            return _value(_json(r), "data", "url")
        except LLMError as e:
            last = e
            if e.code in ("TIMEOUT", "NETWORK", "PARSE_ERROR") and attempt < retries:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise last  # type: ignore[misc]


async def submit_s2v(image_url: str, audio_url: str) -> str:
    r = await _request(
        "POST", f"{settings.dh_base_url.rstrip('/')}/services/aigc/image2video/video-synthesis",
        headers={**_headers(), "Content-Type": "application/json", "X-DashScope-Async": "enable"},
        json={"model": settings.dh_model,
              "input": {"image_url": image_url, "audio_url": audio_url},
              "parameters": {"resolution": settings.dh_resolution}},
    )
    return _value(_json(r), "output", "task_id")


async def poll_s2v(task_id: str, timeout: int = 3600) -> str:
    """轮询任务，成功返回 video_url。查询失败不视为任务失败，继续轮询到 deadline。"""
    deadline = time.monotonic() + timeout
    while True:
        if time.monotonic() > deadline:
            raise LLMError("TIMEOUT", "数字人生成超时")
        await asyncio.sleep(15)
        try:
            r = await _request("GET", f"{settings.dh_base_url.rstrip('/')}/tasks/{task_id}", headers=_headers())
            d = _json(r)
            st = _value(d, "output", "task_status")
        except LLMError:
            # 查询失败不代表任务失败，继续轮询
            continue
        if st == "SUCCEEDED":
            return _value(d, "output", "results", "video_url")
        if st in ("FAILED", "CANCELED"):
            raise LLMError("MODEL_ERROR", f"数字人生成失败：{st}")


async def _download(url: str, out: Path, retries: int = 3) -> Path:
    for attempt in range(retries + 1):
        try:
            r = await _request("GET", url, timeout=180)
            out.write_bytes(r.content)
            return out
        except LLMError as e:
            if e.code in ("TIMEOUT", "NETWORK") and attempt < retries:
                await asyncio.sleep(2 * (attempt + 1))
                continue
            raise
    raise LLMError("NETWORK", "数字人视频下载失败")


def _split_audio(audio_path: str, out_name: str) -> list[Path]:
    seg_dir = AUDIO_DIR / f"{out_name}_segs"
    seg_dir.mkdir(parents=True, exist_ok=True)
    pattern = seg_dir / "seg_%03d.mp3"
    subprocess.run(
        ["ffmpeg", "-i", audio_path, "-f", "segment", "-segment_time", str(settings.dh_segment),
         "-c", "copy", str(pattern)],
        check=True, capture_output=True,
    )
    segs = sorted(seg_dir.glob("seg_*.mp3"))
    # 过滤过短分段（如切分产生的 0.2 秒尾巴），避免数字人接口因音频过短报错导致整个任务降级
    return [s for s in segs if audio_duration(str(s)) >= 1.5]


def _concat_videos(paths: list[Path], out_name: str) -> str:
    list_file = VIDEO_DIR / f"{out_name}_list.txt"
    list_file.write_text("\n".join(f"file '{p}'" for p in paths), encoding="utf-8")
    out = VIDEO_DIR / f"{out_name}.mp4"
    # 重编码 + faststart，保证浏览器/播放器能正常播放音频
    subprocess.run(
        ["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(list_file),
         "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
        check=True, capture_output=True,
    )
    return str(out)


async def generate_talking_video(photo_path: str, audio_path: str, out_name: str) -> str:
    """照片 + 真实配音 → 口型驱动视频。音频超 20 秒自动切段分别生成再拼接。"""
    image_url = await upload_file(photo_path)
    dur = audio_duration(audio_path)

    if dur <= settings.dh_segment:
        segments = [Path(audio_path)]
    else:
        segments = _split_audio(audio_path, out_name)

    video_paths: list[Path] = []
    for i, seg in enumerate(segments):
        audio_url = await upload_file(str(seg))
        task_id = await submit_s2v(image_url, audio_url)
        vurl = await poll_s2v(task_id)
        seg_video = VIDEO_DIR / f"{out_name}_seg{i}.mp4"
        await _download(vurl, seg_video)
        video_paths.append(seg_video)

    if len(video_paths) == 1:
        # 重编码 + faststart，保证浏览器可播放音频
        final = VIDEO_DIR / f"{out_name}.mp4"
        subprocess.run(
            ["ffmpeg", "-i", str(video_paths[0]), "-c:v", "libx264", "-c:a", "aac",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(final)],
            check=True, capture_output=True,
        )
        return str(final)
    return _concat_videos(video_paths, out_name)
