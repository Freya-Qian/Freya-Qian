"""PRD 6.2 漏斗指标聚合：从 events.jsonl + 数据库算各阶段完成率与转化率。

验收时跑 `cd backend && .venv/bin/python metrics.py` 能出数即可。
"""
from __future__ import annotations

import json

from app.core.db import SessionLocal
from app.models import Project
from app.services.observability import EVENTS_PATH

# 漏斗各阶段事件（按流程顺序）
STAGES = [
    "project_created",
    "clarify_generated",
    "brief_generated",
    "competitor_added",
    "evidence_added",
    "positioning_generated",
    "prd_generated",
    "tasks_generated",
    "exported",
]


def _load_events() -> list[dict]:
    if not EVENTS_PATH.exists():
        return []
    events = []
    for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events


def compute_funnel() -> tuple[list[tuple[str, int, float]], int]:
    """返回 (各阶段达成数与完成率列表, 项目基准数)。"""
    events = _load_events()
    by_project: dict[str, set] = {}
    for e in events:
        pid = e.get("project_id") or ""
        by_project.setdefault(pid, set()).add(e.get("event"))

    counts = {stage: sum(1 for evs in by_project.values() if stage in evs) for stage in STAGES}

    db = SessionLocal()
    try:
        total_projects = db.query(Project).count()
    finally:
        db.close()

    base = max(counts.get("project_created", 0), total_projects, 1)
    rows = [(stage, counts.get(stage, 0), counts.get(stage, 0) / base) for stage in STAGES]
    return rows, base


def print_funnel() -> None:
    rows, base = compute_funnel()
    print(f"项目总数（基准）：{base}")
    print(f"{'阶段':<26}{'达成数':>8}{'完成率':>10}")
    print("-" * 44)
    for stage, n, rate in rows:
        print(f"{stage:<26}{n:>8}{rate:>9.1%}")


if __name__ == "__main__":
    print_funnel()
