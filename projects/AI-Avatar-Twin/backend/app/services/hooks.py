"""钩子系统：pre_tool / post_tool 扩展点，用于埋点、审计、内容拦截统一挂载。

钩子异常不影响主循环（对齐 agent-blueprint s04）。
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

# 事件名 → 钩子列表
_HOOKS: dict[str, list[Callable[..., Awaitable[None]]]] = {
    "pre_tool": [],
    "post_tool": [],
}


def register_hook(event: str, fn: Callable[..., Awaitable[None]]) -> None:
    """注册钩子。event 取值：pre_tool / post_tool。"""
    if event not in _HOOKS:
        raise ValueError(f"未知钩子事件：{event}")
    _HOOKS[event].append(fn)


async def run_hooks(event: str, **kwargs: Any) -> None:
    """按序执行某事件的全部钩子；单个钩子异常吞掉，不影响主流程。"""
    for fn in _HOOKS.get(event, []):
        try:
            await fn(**kwargs)
        except Exception:
            # 钩子只做观测/拦截，异常不阻断业务
            continue


def clear_hooks() -> None:
    """清空钩子（测试用）。"""
    for k in _HOOKS:
        _HOOKS[k].clear()
