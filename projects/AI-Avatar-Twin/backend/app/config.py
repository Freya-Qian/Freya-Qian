"""应用配置：从本项目专属 .env 读取，代码不硬编码密钥/模型。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]  # backend/
PROJECT_DIR = BACKEND_DIR.parent  # projects/AI-Avatar-Twin/

load_dotenv(PROJECT_DIR / ".env")

DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
AUDIO_DIR = DATA_DIR / "audio"
VIDEO_DIR = DATA_DIR / "videos"
EXPORT_DIR = DATA_DIR / "exports"
TEMPLATE_DIR = DATA_DIR / "templates"
for _d in (UPLOAD_DIR, AUDIO_DIR, VIDEO_DIR, EXPORT_DIR, TEMPLATE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "avatar_twin.db"


class Settings:
    model_api_key: str = os.getenv("MODEL_API_KEY", "")
    model_base_url: str = os.getenv("MODEL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model_name: str = os.getenv("MODEL_NAME", "qwen-plus")
    model_timeout: float = float(os.getenv("MODEL_TIMEOUT", "60"))
    model_max_retries: int = int(os.getenv("MODEL_MAX_RETRIES", "2"))
    dev_mode: bool = os.getenv("DEV_MODE", "true").lower() in ("true", "1", "yes")
    token_ttl_days: int = int(os.getenv("TOKEN_TTL_DAYS", "7"))
    tts_enabled: bool = os.getenv("TTS_ENABLED", "true").lower() in ("true", "1", "yes")
    tts_api_key: str = os.getenv("TTS_API_KEY", "") or os.getenv("MODEL_API_KEY", "")
    tts_base_url: str = os.getenv("TTS_BASE_URL", "https://dashscope.aliyuncs.com/api/v1")
    tts_model: str = os.getenv("TTS_MODEL", "cosyvoice-v2")
    tts_voice: str = os.getenv("TTS_VOICE", "longxiaochun_v2")
    dh_enabled: bool = os.getenv("DIGITAL_HUMAN_ENABLED", "true").lower() in ("true", "1", "yes")
    dh_api_key: str = os.getenv("DIGITAL_HUMAN_API_KEY", "") or os.getenv("MODEL_API_KEY", "")
    dh_base_url: str = os.getenv("DIGITAL_HUMAN_BASE_URL", "https://dashscope.aliyuncs.com/api/v1")
    dh_model: str = os.getenv("DIGITAL_HUMAN_MODEL", "wan2.2-s2v")
    dh_resolution: str = os.getenv("DIGITAL_HUMAN_RESOLUTION", "480P")
    dh_segment: float = float(os.getenv("DIGITAL_HUMAN_SEGMENT", "19"))
    script_duration: int = int(os.getenv("SCRIPT_DURATION", "30"))
    # 火山引擎即梦数字人（OmniHuman）
    jimeng_enabled: bool = os.getenv("JIMENG_ENABLED", "true").lower() in ("true", "1", "yes")
    jimeng_ak: str = os.getenv("VOLCENGINE_AK", "")
    jimeng_sk: str = os.getenv("VOLCENGINE_SK", "")
    stylize_enabled: bool = os.getenv("STYLIZE_ENABLED", "true").lower() in ("true", "1", "yes")
    stylize_api_key: str = os.getenv("STYLIZE_API_KEY", "") or os.getenv("MODEL_API_KEY", "")
    stylize_base_url: str = os.getenv("STYLIZE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1")
    stylize_model: str = os.getenv("STYLIZE_MODEL", "wan2.6-image")


settings = Settings()
