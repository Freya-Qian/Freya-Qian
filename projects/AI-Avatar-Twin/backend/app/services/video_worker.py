"""视频任务后台执行：单进程串行队列，状态先落库再执行，崩溃可恢复。"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.config import TEMPLATE_DIR, UPLOAD_DIR, settings
from app.core.db import SessionLocal
from app.core.llm import LLMError
from app.models import AvatarProfile, Script, Topic, VideoProject
from app.services import digital_human, engine, jimeng, packaging, stylize, tts, video as video_svc

_queue: asyncio.Queue | None = None


def _safe_error(exc: Exception) -> str:
    # Do not persist upstream bodies, signed URLs, or arbitrary exception text.
    if isinstance(exc, LLMError):
        codes = {"NO_API_KEY", "TIMEOUT", "NETWORK", "MODEL_ERROR", "PARSE_ERROR", "FETCH_ERROR", "UNAUTHORIZED"}
        if exc.code in codes:
            return f"[{exc.code}] 视频服务处理失败，请核对配置及服务商任务状态后再决定是否重试"
    if isinstance(exc, TimeoutError):
        return "[TIMEOUT] 视频服务响应超时"
    return "[INTERNAL_ERROR] 视频处理失败，请联系管理员核查"


def start_worker() -> None:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
        asyncio.create_task(_worker())


def enqueue(video_id: str) -> None:
    assert _queue is not None, "worker 未启动"
    _queue.put_nowait(video_id)


async def _worker() -> None:
    while True:
        video_id = await _queue.get()
        try:
            await _process_video(video_id)
        except Exception:
            logging.getLogger(__name__).error("Video worker failed; exception details suppressed")
        finally:
            _queue.task_done()


def _photo_path(profile: AvatarProfile | None) -> str:
    if profile and profile.avatar_asset_id:
        p = UPLOAD_DIR / profile.avatar_asset_id
        if p.exists():
            return str(p)
    # 模板形象（用户未上传照片时，avatar_type=template）
    if profile:
        t = TEMPLATE_DIR / f"tpl_{profile.template_id or 1}.png"
        if t.exists():
            return str(t)
    return video_svc.ensure_placeholder()


async def _process_video(video_id: str) -> None:
    db = SessionLocal()
    v = None
    try:
        v = db.get(VideoProject, video_id)
        if not v:
            return
        if v.status != "queued":  # 已被取消的任务直接跳过
            return
        v.status = "rendering"
        db.commit()

        script = db.get(Script, v.script_id)
        profile = db.get(AvatarProfile, v.avatar_profile_id) if v.avatar_profile_id else None
        photo = _photo_path(profile)
        # D11：只有本人照片才做 3D 风格化；模板形象本身已是 3D 风格
        if profile and profile.avatar_asset_id:
            photo = await stylize.stylize_avatar(photo)

        # 1. TTS（不可用则降级静音）；去掉【开头钩子】等结构标记，避免被念出来
        audio = await tts.synthesize(video_svc.strip_markers(script.content), video_id)
        dur = await asyncio.to_thread(video_svc.audio_duration, audio)

        # 2. 字幕 + 视频合成 + 封面
        srt_text = video_svc.generate_srt(script.content, dur)
        (video_svc.VIDEO_DIR / f"{video_id}.srt").write_text(srt_text, encoding="utf-8")

        # 数字人：真实配音(.mp3) + 形象（模板或本人照片）→ 口型驱动视频；失败则降级 MoviePy 合成
        mp4 = None
        degrade_note = ""
        if settings.dh_enabled and audio.endswith(".mp3") and profile:
            try:
                if settings.jimeng_enabled:
                    mp4 = await jimeng.generate_talking_video(photo, audio, video_id)
                else:
                    mp4 = await digital_human.generate_talking_video(photo, audio, video_id)
            except Exception as e:
                mp4 = None
                degrade_note = f"数字人服务不可用，已降级为静态合成（无口型）：{_safe_error(e)}"
        if not mp4:
            mp4 = await asyncio.to_thread(video_svc.compose_video, photo, audio, video_id)
        cover = video_svc.make_cover(photo, video_id)

        # 3. 素材包文案（LLM）——选题标题取自 Topic，而非 topic_id
        topic_obj = db.get(Topic, script.topic_id)
        pkg = await packaging.generate_packaging(
            engine._client(), script.content,
            topic_title=(topic_obj.title if topic_obj else ""),
            platform=script.platform,
        )
        pkg_dict = pkg.model_dump()

        # 4. 打包 ZIP
        script_md = f"# 口播脚本\n\n{script.content}\n\n## 来源\n" + "\n".join(f"- {u}" for u in (script.source_urls or []))
        zip_path = await asyncio.to_thread(
            video_svc.build_package, mp4, cover, srt_text, script_md, pkg_dict,
            script.source_urls or [], video_id,
        )

        v.video_url = f"/api/v1/videos/{video_id}/file"
        v.cover_url = f"/api/v1/videos/{video_id}/cover"
        v.subtitle_url = f"/api/v1/videos/{video_id}/subtitle"
        v.export_package_url = f"/api/v1/videos/{video_id}/export"
        v.error_message = degrade_note  # 成功但降级时也记录降级原因
        v.status = "success"
        db.commit()
    except Exception as e:
        if v is not None:
            v.status = "failed"
            v.error_message = _safe_error(e)
            db.commit()
    finally:
        db.close()
