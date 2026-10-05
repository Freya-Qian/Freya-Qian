"""Agent Loop（s01）：模型自主决策，循环调用工具，直到脚本自检合格或步数上限。

对齐 agent-blueprint 核心循环：messages → model → tool_use → 结果 → 循环。
"""
from __future__ import annotations

import json
from typing import AsyncIterator

from app.core.llm import LLMClient, LLMError
from app.services import evaluator, hooks, prompts, tools
from app.services.parser import parse_json

AGENT_MAX_STEPS = 20
# 硬闭环门（s17）：脚本评估不通过时最多自动重写次数，超过则交还人工审核
MAX_SCRIPT_REWRITES = 2


def _build_user_prompt(goal: str, history: list[dict]) -> str:
    """把目标 + 历史动作/工具结果拼成单条 user prompt（LLMClient 只收 system+user）。"""
    parts = [f"用户目标：{goal}", "", "以下是此前的执行记录："]
    if not history:
        parts.append("（无，请开始第一步）")
    for h in history:
        role = "助手动作" if h["role"] == "assistant" else "工具结果"
        parts.append(f"[{role}] {h['content']}")
    parts.append("")
    parts.append("请继续：判断下一步要调用哪个工具（或已经完成就输出 finish）。")
    return "\n".join(parts)


async def _evaluate_script(client: LLMClient, ctx: dict) -> dict:
    """硬闭环门（s17）：独立评估当前脚本是否达标，返回 {passed, reason, scores}。"""
    state = ctx["state"]
    script = state.get("script")
    if not script:
        return {"passed": True, "reason": "无脚本，跳过评估", "scores": {}}
    topics = state.get("topics", [])
    idx = state.get("script_topic_index", 0)
    topic = topics[idx] if topics and idx < len(topics) else {}
    ev = await evaluator.evaluate_script(
        client,
        script.get("content", ""),
        topic.get("title", ""),
        script.get("fact_claims", []),
        script.get("source_urls", []),
    )
    return {"passed": ev.passed, "reason": ev.reason, "scores": ev.scores}


def _mark_quality_risk(script: dict) -> None:
    """评估多次不通过：给脚本追加风险标注，交还人工审核。"""
    flags = list(script.get("risk_flags") or [])
    msg = "质量待人工审核（自动评估多次未通过）"
    if msg not in flags:
        flags.append(msg)
    script["risk_flags"] = flags


async def run_agent(client: LLMClient, user, goal: str, profile=None) -> AsyncIterator[dict]:
    """流式执行 Agent。事件：start → step → tool_result → ... → done。

    产出最终事件 done 的 status：done（有脚本）/ incomplete（无脚本）/ max_steps。
    """
    ctx: dict = {"user": user, "profile": profile, "state": {}}
    history: list[dict] = []

    yield {"type": "start", "goal": goal}

    for step in range(1, AGENT_MAX_STEPS + 1):
        user_prompt = _build_user_prompt(goal, history)
        system_prompt = prompts.AGENT_SYSTEM.format(tools=tools.tool_descriptions())
        text = await client.complete(system_prompt, user_prompt,
                                     max_tokens=1500, temperature=0.4)

        # 宽容解析：模型偶发不输出 JSON 时，把原文当 thought 并直接结束（不硬卡）
        try:
            action = parse_json(text)
        except LLMError:
            action = {"thought": text[:200], "action": "finish", "action_input": {}}

        action_name = action.get("action", "finish")
        action_input = action.get("action_input", {}) or {}

        yield {"type": "step", "step": step,
               "thought": action.get("thought", ""),
               "action": action_name}

        if action_name == "finish":
            script = ctx["state"].get("script")
            if not script:
                yield {"type": "done", "status": "incomplete",
                       "script": None, "steps": step}
                return
            # 硬闭环门（s17）：finish 前强制独立评估；不达标则回写重写（最多 MAX_SCRIPT_REWRITES 次）
            if not ctx["state"].get("_eval_passed"):
                ev = await _evaluate_script(client, ctx)
                yield {"type": "eval", "passed": ev["passed"],
                       "reason": ev["reason"], "scores": ev["scores"]}
                if ev["passed"]:
                    ctx["state"]["_eval_passed"] = True
                    yield {"type": "done", "status": "done",
                           "script": script, "steps": step}
                    return
                fail_count = ctx["state"].get("_eval_fail_count", 0) + 1
                ctx["state"]["_eval_fail_count"] = fail_count
                if fail_count > MAX_SCRIPT_REWRITES:
                    # 重写次数用尽：标风险标注后交还人工审核
                    _mark_quality_risk(script)
                    yield {"type": "done", "status": "done",
                           "script": script, "steps": step}
                    return
                # 回写评估反馈，继续循环让模型重写
                history.append({"role": "assistant",
                                "content": json.dumps(action, ensure_ascii=False)})
                history.append({"role": "tool",
                                "content": json.dumps({
                                    "tool": "evaluate_script",
                                    "result": {"passed": False, "reason": ev["reason"]},
                                    "hint": "脚本未通过质量自检，请调用 generate_script 重写（修正上述问题），或调用 generate_topics 换选题后重新生成。",
                                }, ensure_ascii=False)})
                continue
            yield {"type": "done", "status": "done",
                   "script": script, "steps": step}
            return

        # 执行工具（pre/post 钩子挂埋点/审计；异常不阻断主循环）
        await hooks.run_hooks("pre_tool", tool=action_name, args=action_input)
        try:
            result = await tools.execute_tool(client, action_name, action_input, ctx)
        except LLMError as e:
            result = {"error": e.message}
        except Exception as e:  # 工具异常兜底，避免 Agent 因单点崩溃退出
            result = {"error": f"{type(e).__name__}: {e}"}
        await hooks.run_hooks("post_tool", tool=action_name, args=action_input, result=result)

        # 脚本被重新生成 → 重置质量门，下一轮 finish 时重新评估
        if action_name == "generate_script" and not result.get("error"):
            ctx["state"]["_eval_passed"] = False

        yield {"type": "tool_result", "tool": action_name, "result": result}

        history.append({"role": "assistant",
                        "content": json.dumps(action, ensure_ascii=False)})
        history.append({"role": "tool",
                        "content": json.dumps(result, ensure_ascii=False)})

    # 达到步数上限：交还用户当前进度
    yield {"type": "done", "status": "max_steps",
           "script": ctx["state"].get("script"), "steps": AGENT_MAX_STEPS}
