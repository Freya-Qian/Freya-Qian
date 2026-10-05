"""照片→3D 渲染风风格化（通义万相参考生图 wan2.6-image）。失败自动降级返回原照片。"""
from __future__ import annotations

import asyncio
import base64
import hashlib
from pathlib import Path

import httpx
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.config import UPLOAD_DIR, settings

STYLE_PROMPT = (
    "把这张照片转换成3D渲染风格的数字人形象，皮克斯动画质感，"
    "保留面部特征和五官比例，立体感强，适合做短视频口播主播，"
    "正面半身像，竖屏"
)


def _cache_path(photo_path: str) -> Path:
    digest = hashlib.sha256(Path(photo_path).read_bytes()).hexdigest()[:16]
    return UPLOAD_DIR / f"stylized_{digest}.png"


def _local_stylize_avatar(photo_path: str, cache: Path) -> str:
    try:
        source = Image.open(photo_path).convert("RGB")
        source.thumbnail((720, 920), Image.Resampling.LANCZOS)

        smoothed = source.filter(ImageFilter.SMOOTH_MORE)
        smoothed = ImageEnhance.Color(smoothed).enhance(1.24)
        smoothed = ImageEnhance.Contrast(smoothed).enhance(1.18)
        smoothed = ImageEnhance.Sharpness(smoothed).enhance(1.35)

        poster = ImageOps.posterize(smoothed, 5)
        edges = smoothed.convert("L").filter(ImageFilter.FIND_EDGES)
        edges = ImageOps.invert(edges).point(lambda p: 255 if p > 215 else 230)
        rendered = Image.composite(poster, smoothed, edges)

        canvas = Image.new("RGB", (720, 1280), "#0d131b")
        bg = Image.new("RGB", canvas.size, "#172234")
        glow = Image.new("RGB", canvas.size, "#23493f").filter(ImageFilter.GaussianBlur(90))
        canvas = Image.blend(canvas, bg, 0.45)
        canvas = Image.blend(canvas, glow, 0.22)

        shadow = Image.new("RGBA", rendered.size, (0, 0, 0, 0))
        alpha = Image.new("L", rendered.size, 180).filter(ImageFilter.GaussianBlur(22))
        shadow.putalpha(alpha)
        x = (canvas.width - rendered.width) // 2
        y = max(110, (canvas.height - rendered.height) // 2 - 10)
        canvas.paste(shadow.convert("RGB"), (x + 16, y + 28), shadow)
        canvas.paste(rendered, (x, y))

        vignette = Image.radial_gradient("L").resize(canvas.size)
        vignette = ImageOps.invert(vignette).point(lambda p: int(p * 0.35))
        overlay = Image.new("RGB", canvas.size, "#000000")
        canvas = Image.composite(overlay, canvas, vignette)
        cache.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(cache, "PNG")
        return str(cache)
    except Exception:
        return photo_path


async def stylize_avatar(photo_path: str, force: bool = False) -> str:
    """照片→3D风格化形象，返回风格化图片路径；失败或未启用则返回原照片。"""
    cache = _cache_path(photo_path)
    if force:
        try:
            cache.unlink(missing_ok=True)
        except OSError:
            pass
    if cache.exists():
        return str(cache)
    if not settings.stylize_enabled or not settings.stylize_api_key:
        return _local_stylize_avatar(photo_path, cache)

    photo_bytes = Path(photo_path).read_bytes()
    ext = Path(photo_path).suffix.lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    b64 = base64.b64encode(photo_bytes).decode("ascii")

    payload = {
        "model": settings.stylize_model,
        "input": {
            "messages": [{
                "role": "user",
                "content": [
                    {"text": STYLE_PROMPT},
                    {"image": f"data:{mime};base64,{b64}"},
                ],
            }]
        },
        "parameters": {"size": "1280*720", "n": 1, "watermark": False},
    }

    base = settings.stylize_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.stylize_api_key}"}
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{base}/services/aigc/image-generation/generation",
                json=payload,
                headers={**headers, "X-DashScope-Async": "enable"},
            )
            if resp.status_code != 200:
                return _local_stylize_avatar(photo_path, cache)
            task_id = (resp.json().get("output") or {}).get("task_id")
            if not task_id:
                return _local_stylize_avatar(photo_path, cache)

            url = None
            for _ in range(60):  # 最多约 3 分钟
                await asyncio.sleep(3)
                r = await client.get(f"{base}/tasks/{task_id}", headers=headers)
                out = (r.json().get("output") or {}) if r.status_code == 200 else {}
                status = out.get("task_status")
                if status == "SUCCEEDED":
                    url = next(
                        (p.get("image") for c in out.get("choices", [])
                         for p in c.get("message", {}).get("content", [])
                         if isinstance(p, dict) and p.get("image")),
                        None,
                    )
                    break
                if status in ("FAILED", "CANCELED", "UNKNOWN"):
                    return _local_stylize_avatar(photo_path, cache)

            if not url:
                return _local_stylize_avatar(photo_path, cache)

            if url.startswith("data:"):
                data = url.split(",", 1)[1]
                cache.write_bytes(base64.b64decode(data))
            else:
                img = await client.get(url)
                if img.status_code == 200:
                    cache.write_bytes(img.content)
                else:
                    return _local_stylize_avatar(photo_path, cache)
            return str(cache)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return _local_stylize_avatar(photo_path, cache)  # 任何失败都降级本地预览，保证页面不空白
