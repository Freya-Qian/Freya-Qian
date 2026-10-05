"""视频合成：SRT 字幕、封面、照片+音频→MP4（MoviePy）、素材包 ZIP。"""
from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from moviepy import AudioFileClip, ImageClip

from app.config import EXPORT_DIR, UPLOAD_DIR, VIDEO_DIR
from app.services import tts

VIDEO_W, VIDEO_H = 1080, 1920  # 9:16
_PLACEHOLDER = UPLOAD_DIR / "_placeholder.jpg"


def ensure_placeholder() -> str:
    """无照片时的占位图（ffmpeg 生成纯色 9:16 图）。"""
    if not _PLACEHOLDER.exists():
        subprocess.run(
            ["ffmpeg", "-f", "lavfi", "-i", "color=c=0x2b3a4a:s=1080x1920",
             "-frames:v", "1", "-y", str(_PLACEHOLDER)],
            check=True, capture_output=True,
        )
    return str(_PLACEHOLDER)


# ---------- SRT ----------


def strip_markers(content: str) -> str:
    """去掉脚本里的【开头钩子】等结构标记，用于 TTS 配音（不把标记念出来）。"""
    return re.sub(r"【[^】]*】", "", content).strip()


def _split_sentences(content: str) -> list[str]:
    """按【模块】与标点切分句子。"""
    text = strip_markers(content)
    parts = re.split(r"(?<=[。！？；!?;])\s*|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def generate_srt(content: str, duration: float | None = None) -> str:
    """生成 SRT 文本：按字数占比分配时长。纯函数，重点单测。"""
    segs = _split_sentences(content)
    total = duration if duration else tts.estimate_duration(content)
    if not segs:
        return ""
    total_chars = sum(len(s) for s in segs) or 1
    lines = []
    cursor = 0.0
    for i, s in enumerate(segs, 1):
        seg_dur = max(0.8, total * len(s) / total_chars)
        start = cursor
        end = cursor + seg_dur
        cursor = end
        lines.append(f"{i}\n{_fmt_ts(start)} --> {_fmt_ts(end)}\n{s}\n")
    return "\n".join(lines)


def _fmt_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ---------- 音频时长 / 视频合成 ----------


def audio_duration(path: str) -> float:
    try:
        return float(AudioFileClip(path).duration)
    except Exception:
        return 3.0


def compose_video(photo_path: str, audio_path: str, out_name: str) -> str:
    """照片 + 音频 → 9:16 MP4（照片缩放居中裁剪）。"""
    out = VIDEO_DIR / f"{out_name}.mp4"
    audio = AudioFileClip(audio_path)
    img = ImageClip(photo_path)
    scale = max(VIDEO_W / img.w, VIDEO_H / img.h)
    img = img.resized(scale)
    img = img.cropped(x_center=img.w / 2, y_center=img.h / 2, width=VIDEO_W, height=VIDEO_H)
    img = img.with_duration(audio.duration)
    clip = img.with_audio(audio)
    clip.write_videofile(str(out), fps=24, codec="libx264", audio_codec="aac", logger=None)
    return str(out)


# ---------- 封面 / 素材包 ----------


def make_cover(photo_path: str, out_name: str) -> str:
    """封面：直接用照片（复制到导出目录）。"""
    src = Path(photo_path)
    dst = VIDEO_DIR / f"{out_name}_cover{src.suffix}"
    shutil.copyfile(src, dst)
    return str(dst)


def build_package(video_path: str, cover_path: str, srt_text: str, script_md: str,
                  packaging: dict, sources: list[str], out_name: str) -> str:
    """打包素材包 ZIP。"""
    out = EXPORT_DIR / f"{out_name}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(video_path, "video.mp4")
        if cover_path:
            z.write(cover_path, f"cover{Path(cover_path).suffix}")
        if srt_text:
            z.writestr("subtitle.srt", srt_text)
        z.writestr("script.md", script_md)
        title = packaging.get("title", "")
        desc = packaging.get("description", "")
        tags = " ".join(f"#{t}" for t in packaging.get("tags", []))
        z.writestr("文案.txt", f"标题：{title}\n简介：{desc}\n标签：{tags}\n")
        z.writestr("来源清单.txt", "\n".join(sources or []))
    return str(out)
