"""宽容 JSON 解析器（纯函数，重点单测对象）。

模型不按格式输出是常态：可能带 ```json 围栏、JSON 外有解释、尾逗号等。
本模块兼容多种常见坏格式，解析失败抛出 LLMError，由调用方走有限重试。
"""
from __future__ import annotations

import json
import re

from app.core.llm import LLMError


def _strip_fences(text: str) -> str:
    """去掉 ```json ... ``` 或 ``` ... ``` 围栏。"""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", t, re.DOTALL)
    if m:
        return m.group(1).strip()
    return t


def _extract_json_object(text: str) -> str:
    """截取首个 '{' 到最后一个 '}' 之间的内容。"""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMError("PARSE_ERROR", "模型输出不是合法 JSON")
    return text[start : end + 1]


def _fix_trailing_commas(text: str) -> str:
    """去掉对象/数组里的尾逗号。"""
    return re.sub(r",\s*([}\]])", r"\1", text)


def parse_json(text: str) -> dict:
    """尽力把模型文本解析成 dict。失败抛 LLMError(PARSE_ERROR)。"""
    if not text or not text.strip():
        raise LLMError("PARSE_ERROR", "模型输出为空")
    t = _strip_fences(text)
    t = _extract_json_object(t)

    for candidate in (t, _fix_trailing_commas(t)):
        try:
            obj = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            return obj

    raise LLMError("PARSE_ERROR", "模型输出无法解析为 JSON 对象")
