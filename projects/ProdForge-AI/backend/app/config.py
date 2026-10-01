"""应用配置：从本项目专属 .env 读取，代码不硬编码密钥/模型。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]  # backend/
PROJECT_DIR = BACKEND_DIR.parent  # projects/AI产品工厂/

load_dotenv(PROJECT_DIR / ".env")

DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "product_factory.db"

# MVP 匿名本地用户（无账号体系，所有项目归属该用户；User 表预埋，V1 迁移云端不返工）
DEFAULT_USER_ID = "local_user"


class Settings:
    model_api_key: str = os.getenv("MODEL_API_KEY", "")
    model_base_url: str = os.getenv("MODEL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model_name: str = os.getenv("MODEL_NAME", "qwen-plus")
    model_timeout: float = float(os.getenv("MODEL_TIMEOUT", "120"))
    model_max_retries: int = int(os.getenv("MODEL_MAX_RETRIES", "2"))
    project_budget_cny: float = float(os.getenv("PROJECT_BUDGET_CNY", "10"))
    dev_mode: bool = os.getenv("DEV_MODE", "true").lower() in ("true", "1", "yes")


settings = Settings()

# 成本估算单价（元/千 token，qwen-plus 估算；MVP 只要数量级正确即可，不必精确到分）
TOKEN_PRICE_PER_1K = 0.002


def save_model_config(model_api_key: str, model_name: str | None = None,
                      model_base_url: str | None = None) -> None:
    """写回 .env 并热更新内存 settings 单例（无需重启后端）。

    安全：只写 .env（已 gitignore），不进库/不进日志；Key 不在此回显。
    """
    env_path = PROJECT_DIR / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []

    updates = {"MODEL_API_KEY": model_api_key.strip()}
    if model_name:
        updates["MODEL_NAME"] = model_name.strip()
    if model_base_url:
        updates["MODEL_BASE_URL"] = model_base_url.strip().rstrip("/")

    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={val}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")

    # 热更新内存单例
    settings.model_api_key = updates["MODEL_API_KEY"]
    if "MODEL_NAME" in updates:
        settings.model_name = updates["MODEL_NAME"]
    if "MODEL_BASE_URL" in updates:
        settings.model_base_url = updates["MODEL_BASE_URL"]
