"""模型输出的确定性解析（纯函数，重点单测）。

用括号配对扫描定位第一个 { 到与之匹配的 }，忽略字符串内与嵌套对象的括号，
比 rfind("}") 更稳（多 JSON / 尾部夹带 } 时不截错）。
"""
from __future__ import annotations

import json

from app.core.llm import LLMError


def _parse_object(fragment: str) -> dict:
    try:
        obj = json.loads(fragment)
    except ValueError as e:
        raise LLMError("PARSE_ERROR", "模型输出 JSON 解析失败") from e
    if not isinstance(obj, dict):
        raise LLMError("PARSE_ERROR", "模型输出不是 JSON 对象")
    return obj


def extract_json(text: str) -> dict:
    """从模型输出中提取 JSON 对象：容忍 Markdown 代码块与前后杂文。"""
    text = (text or "").strip()
    start = text.find("{")
    if start == -1:
        raise LLMError("PARSE_ERROR", "模型输出不含有效 JSON 结构")

    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return _parse_object(text[start:i + 1])
    raise LLMError("PARSE_ERROR", "模型输出 JSON 结构不完整")
