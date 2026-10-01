"""轻量埋点：把关键阶段事件写入 data/events.jsonl（MVP 不引第三方）。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import DATA_DIR

EVENTS_PATH: Path = DATA_DIR / "events.jsonl"


def record_event(event: str, project_id: str = "", **fields) -> None:
    """追加一条事件到 events.jsonl。埋点失败不影响主流程。"""
    try:
        with EVENTS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "project_id": project_id,
                **fields,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 埋点失败不影响主流程
