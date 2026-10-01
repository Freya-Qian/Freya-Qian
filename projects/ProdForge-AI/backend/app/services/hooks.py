"""轻量钩子：pre_tool / post_tool 两阶段，钩子异常不影响主流程（P2-1）。

⚠️ 框架已提供、迁移未做：当前 register_hook/run_hooks 全仓库零调用，证据审计、
埋点、成本累计仍是内联调用。后续可逐步迁移为 post_tool 钩子。
"""
from __future__ import annotations

from typing import Callable

_HOOKS: dict[str, list[Callable]] = {"pre_tool": [], "post_tool": []}


def register_hook(stage: str, fn: Callable) -> None:
    """注册一个钩子到指定阶段（pre_tool / post_tool）。"""
    _HOOKS.setdefault(stage, []).append(fn)


async def run_hooks(stage: str, **ctx) -> None:
    """按序执行某阶段全部钩子，单个钩子异常不影响主流程与后续钩子。"""
    for fn in _HOOKS.get(stage, []):
        try:
            await fn(**ctx)
        except Exception:
            pass
