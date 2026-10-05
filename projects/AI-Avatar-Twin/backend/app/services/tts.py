"""TTS：口播稿转配音（阿里云百炼 CosyVoice）。未配 Key 或失败时降级为静音音频。"""
from __future__ import annotations

import wave

import httpx

from app.config import AUDIO_DIR, settings

CHARS_PER_SECOND = 4.5


def estimate_duration(text: str) -> float:
    """按中文字数估算口播时长（秒），用于静音降级与 SRT 分片。"""
    n = len([c for c in text if not c.isspace()])
    return max(3.0, n / CHARS_PER_SECOND)


def _silent_audio(path, duration: float) -> str:
    framerate = 16000
    nframes = int(duration * framerate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00\x00" * nframes)
    return str(path)


async def synthesize(text: str, out_name: str) -> str:
    """口播稿转音频，返回音频文件路径。TTS 失败则降级为静音 WAV。"""
    if settings.tts_enabled and settings.tts_api_key:
        try:
            url = f"{settings.tts_base_url.rstrip('/')}/services/audio/tts/SpeechSynthesizer"
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {settings.tts_api_key}", "Content-Type": "application/json"},
                    json={"model": settings.tts_model,
                          "input": {"text": text, "voice": settings.tts_voice, "format": "mp3"}},
                )
            if resp.status_code == 200:
                audio_url = (resp.json().get("output", {}).get("audio", {}).get("url", ""))
                if audio_url:
                    async with httpx.AsyncClient(timeout=60) as client:
                        ar = await client.get(audio_url)
                    if ar.status_code == 200 and ar.content:
                        mp3 = AUDIO_DIR / f"{out_name}.mp3"
                        mp3.write_bytes(ar.content)
                        return str(mp3)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            pass
    return _silent_audio(AUDIO_DIR / f"{out_name}.wav", estimate_duration(text))
