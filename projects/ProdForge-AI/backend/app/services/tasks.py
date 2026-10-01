"""研发任务拆解（M3 服务）：按模块/优先级生成可执行、可验收的任务。"""
from __future__ import annotations

import json

from app.core.llm import LLMClient, LLMError
from app.services.parser import extract_json
from app.services.prompts import TASKS_SYSTEM, TASK_MODULES


def _normalize_tasks(raw: list) -> list[dict]:
    result = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        module = str(item.get("module", "")).strip()
        if module not in TASK_MODULES:
            module = "后端"
        priority = str(item.get("priority", "")).strip()
        if priority not in ("P0", "P1", "P2"):
            priority = "P1"
        result.append({
            "module": module,
            "title": title,
            "description": str(item.get("description", "")).strip(),
            "priority": priority,
            "acceptance_criteria": str(item.get("acceptance_criteria", "")).strip(),
            "dependencies": [d for d in (item.get("dependencies") or []) if isinstance(d, str)],
            "source_refs": [s for s in (item.get("source_refs") or []) if isinstance(s, str)],
        })
    # 悬空依赖校验：过滤不存在的依赖标题
    titles = {t["title"] for t in result}
    for t in result:
        t["dependencies"] = [d for d in t["dependencies"] if d in titles]
    return result


async def generate_tasks(client: LLMClient, prd_sections: list[dict],
                         positioning: dict, evidences: list[dict]) -> list[dict]:
    """根据 PRD 拆解研发任务。"""
    prd_text = "\n\n".join(f"# {s['title']}\n{s['content']}" for s in prd_sections)
    ev_text = "\n".join(f"- {e['ref_key']}：{e['structured_claim']}" for e in evidences)
    user = (
        "PRD 章节内容：\n" + prd_text + "\n\n"
        "产品定位：\n" + json.dumps({
            "one_liner": positioning.get("one_liner", ""),
            "differentiators": positioning.get("differentiators", []),
        }, ensure_ascii=False, indent=1) + "\n\n"
        "竞品证据卡：\n" + ev_text + "\n\n"
        "请拆解研发任务。"
    )
    text = await client.complete(TASKS_SYSTEM, user, max_tokens=4000, temperature=0.5)
    try:
        data = extract_json(text)
    except LLMError as first_err:
        retry_user = (
            user + "\n\n"
            f"你上一次的输出不是合法 JSON（错误：{first_err.message}）。"
            "请严格只输出一个 JSON 对象，不要任何解释或代码块标记。"
        )
        text = await client.complete(TASKS_SYSTEM, retry_user, max_tokens=4000, temperature=0.4)
        data = extract_json(text)
    return _normalize_tasks(data.get("tasks"))
