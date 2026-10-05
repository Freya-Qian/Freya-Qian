"""内容安全基础过滤：关键词 + 破坏性模式拦截（对齐脑洞游戏 guard.py，适配 AI 行业内容）。

正式公开上线前需升级为专业内容审核；本版只满足 MVP 小范围试用。
"""
from __future__ import annotations

import re

# 敏感/破坏性关键词（MVP 基础版，按需增删）
_BLOCK_KEYWORDS = [
    "自杀", "自残", "杀人", "血腥", "色情", "赌博", "毒品", "虐待",
    "暴恐", "政治敏感", "颠覆国家",
]

# 高危表述模式
_VIOLENCE_PATTERNS = [
    r"如何(制造|制作|合成).{0,8}(炸弹|毒药|武器|毒品)",
    r"(教|指导).{0,6}(杀人|自杀|犯罪)",
]


def content_guard(text: str) -> tuple[bool, str]:
    """返回 (是否放行, 拒绝原因)。空/过短由 Pydantic 层处理，这里只做语义层。"""
    t = (text or "").strip()
    low = t.lower()
    for kw in _BLOCK_KEYWORDS:
        if kw in low:
            return False, "内容包含不适宜信息，请更换表述"
    for pat in _VIOLENCE_PATTERNS:
        if re.search(pat, t):
            return False, "内容涉及高风险信息，暂不支持"
    return True, ""
