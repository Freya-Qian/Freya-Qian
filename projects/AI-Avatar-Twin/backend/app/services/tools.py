"""工具池（s02）：Agent 可调用的工具注册表 + 元信息 + 分派执行。

业务能力复用 engine/fetcher 现有函数；Agent Loop（agent.py）通过本模块分派。
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.core.llm import LLMClient, LLMError
from app.services import engine, evaluator, fetcher
from app.services.guard import content_guard

# ---------- 工具元信息 ----------

TOOLS: dict[str, dict[str, Any]] = {
    "fetch_source": {
        "description": "抓取一个网页链接的正文，作为选题素材",
        "parameters": {"url": "string，网页链接"},
        "permission": "allow",
    },
    "summarize": {
        "description": "对已抓取的正文生成结构化摘要（标题/摘要/关键词/可信度）",
        "parameters": {},
        "permission": "allow",
    },
    "generate_topics": {
        "description": "基于摘要生成 3 个候选短视频选题（含角度/看点/风险/评分）",
        "parameters": {},
        "permission": "allow",
    },
    "fact_check": {
        "description": "对选题的关键事实做来源标注与风险提示",
        "parameters": {"topic_index": "int，选题下标（0 起）"},
        "permission": "allow",
    },
    "generate_script": {
        "description": "为指定选题生成口播脚本（含来源引用与风险标注，默认 30 秒）",
        "parameters": {"topic_index": "int，选题下标（0 起）"},
        "permission": "allow",
    },
    "evaluate_script": {
        "description": "自检当前脚本是否达标（回应选题/事实有据/语言通顺）",
        "parameters": {},
        "permission": "allow",
    },
}


def tool_descriptions() -> str:
    """生成系统提示词用的工具清单文本。"""
    lines = []
    for name, meta in TOOLS.items():
        lines.append(f"- {name}：{meta['description']}；参数 {meta['parameters']}")
    return "\n".join(lines)


# ---------- 工具执行 ----------

def _make_source(item: dict) -> SimpleNamespace:
    """构造 engine 函数需要的轻量 source 对象。"""
    return SimpleNamespace(
        title=item.get("title", ""),
        original_url=item.get("url", ""),
        content_text=item.get("content", ""),
        summary=item.get("summary", ""),
        keywords=item.get("keywords", []),
        is_official=0,
        credibility_score=0,
        video_potential_score=0,
        status="fetched",
    )


def _make_topic(item: dict) -> SimpleNamespace:
    """构造 engine 函数需要的轻量 topic 对象。"""
    return SimpleNamespace(
        title=item.get("title", ""),
        angle=item.get("angle", ""),
        one_liner=item.get("one_liner", ""),
        key_facts=item.get("key_facts", []),
        source_urls=item.get("source_urls", []),
        risk_flags=item.get("risk_flags", []),
    )


async def _collect_script(client: LLMClient, topic, source, profile) -> dict:
    """把流式脚本生成收拢成最终 script dict。"""
    script = None
    async for ev in engine.generate_script_stream(client, topic, source, profile):
        if ev["type"] == "done":
            script = ev["script"]
        elif ev["type"] == "error":
            raise LLMError(ev["error"].get("code", "MODEL_ERROR"),
                           ev["error"].get("message", "脚本生成失败"))
    if not script:
        raise LLMError("MODEL_ERROR", "脚本生成失败")
    return script


async def execute_tool(client: LLMClient, name: str, args: dict, ctx: dict) -> dict:
    """按工具名分派执行。ctx 含 user/profile/state。返回工具结果（供模型读）。"""
    state: dict = ctx["state"]
    profile = ctx.get("profile")

    if name == "fetch_source":
        url = (args or {}).get("url", "").strip()
        if not url:
            return {"error": "缺少 url 参数"}
        fetched = await fetcher.fetch_url(url)
        # 内容安全：抓取到的正文先过 guard（防敏感内容）
        ok, reason = content_guard(fetched["title"] + " " + fetched["content_text"][:2000])
        if not ok:
            return {"error": reason}
        src = {
            "url": url,
            "title": fetched["title"],
            "content": fetched["content_text"][:6000],
        }
        state["sources"] = state.get("sources", [])
        state["sources"].append(src)
        state["current_source"] = src
        return {"ok": True, "title": src["title"],
                "content_preview": src["content"][:300], "index": len(state["sources"]) - 1}

    if name == "summarize":
        src = state.get("current_source")
        if not src:
            return {"error": "请先 fetch_source 抓取素材"}
        obj = _make_source(src)
        await engine.summarize_source(client, obj)
        src["summary"] = obj.summary
        src["keywords"] = obj.keywords
        state["current_source"] = src
        return {"ok": True, "summary": obj.summary, "keywords": obj.keywords,
                "credibility_score": obj.credibility_score,
                "video_potential_score": obj.video_potential_score}

    if name == "generate_topics":
        src = state.get("current_source")
        if not src or not src.get("summary"):
            return {"error": "请先 fetch_source 并 summarize"}
        obj = _make_source(src)
        topics = await engine.generate_topics(client, obj)
        topic_dicts = [t.model_dump() if hasattr(t, "model_dump") else t for t in topics]
        state["topics"] = topic_dicts
        brief = [{"index": i, "title": t["title"], "angle": t.get("angle", "")}
                 for i, t in enumerate(topic_dicts)]
        return {"ok": True, "topics": brief}

    if name == "fact_check":
        idx = int((args or {}).get("topic_index", 0))
        topics = state.get("topics", [])
        if not topics or idx >= len(topics):
            return {"error": "topic_index 越界，请先 generate_topics"}
        t = topics[idx]
        # 事实核查复用兜底：来源不足标单一来源；返回风险提示
        flags = list(t.get("risk_flags", []))
        flags = engine._detect_single_source(t.get("source_urls", []), flags)
        t["risk_flags"] = flags
        state["topics"][idx] = t
        return {"ok": True, "risk_level": t.get("risk_level", "low"),
                "risk_flags": flags, "source_urls": t.get("source_urls", [])}

    if name == "generate_script":
        idx = int((args or {}).get("topic_index", 0))
        topics = state.get("topics", [])
        src = state.get("current_source")
        if not topics or idx >= len(topics):
            return {"error": "topic_index 越界，请先 generate_topics"}
        topic = _make_topic(topics[idx])
        source = _make_source(src or {})
        # 内容安全：脚本生成前对选题标题做 guard
        ok, reason = content_guard(topic.title)
        if not ok:
            return {"error": reason}
        script = await _collect_script(client, topic, source, profile)
        # 内容安全：生成的脚本正文（UGC 出口）也要过 guard
        ok, reason = content_guard(script.get("content", ""))
        if not ok:
            return {"error": reason}
        state["script"] = script
        state["script_topic_index"] = idx
        return {"ok": True, "script_preview": script.get("content", "")[:300],
                "fact_claims": script.get("fact_claims", []),
                "risk_flags": script.get("risk_flags", []),
                "source_urls": script.get("source_urls", [])}

    if name == "evaluate_script":
        script = state.get("script")
        if not script:
            return {"error": "请先 generate_script"}
        topics = state.get("topics", [])
        idx = state.get("script_topic_index", 0)
        topic = topics[idx] if topics and idx < len(topics) else {}
        ev = await evaluator.evaluate_script(
            client, script.get("content", ""),
            topic.get("title", ""),
            script.get("fact_claims", []),
            script.get("source_urls", []),
        )
        return {"ok": True, "passed": ev.passed, "reason": ev.reason}

    return {"error": f"未知工具：{name}"}
