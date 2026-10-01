"""模型输出解析器单测（纯函数重点覆盖）。"""
from __future__ import annotations

import pytest

from app.core.llm import LLMError
from app.services.parser import extract_json


def test_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_json_with_code_fence():
    text = '好的，输出如下：\n```json\n{"a": 1}\n```\n以上。'
    assert extract_json(text) == {"a": 1}


def test_json_with_surrounding_text():
    text = '这是结果：{"questions": [{"dimension": "目标用户"}]} 结束'
    assert extract_json(text)["questions"][0]["dimension"] == "目标用户"


def test_invalid_json_raises():
    with pytest.raises(LLMError) as e:
        extract_json("不是 JSON，只是一段文字")
    assert e.value.code == "PARSE_ERROR"


def test_non_object_raises():
    with pytest.raises(LLMError) as e:
        extract_json("[1, 2, 3]")
    assert e.value.code == "PARSE_ERROR"


def test_nested_json_with_braces_in_string():
    text = '{"a": {"b": "包含{和}的字符串"}, "c": [1, 2]}'
    obj = extract_json(text)
    assert obj["a"]["b"] == "包含{和}的字符串"
    assert obj["c"] == [1, 2]


def test_trailing_garbage_after_json():
    # 尾部夹带另一个 } 和第二个 JSON，也应只提取第一个完整对象
    text = '{"a": 1} 后面还有 } 和 {"x": 2}'
    obj = extract_json(text)
    assert obj == {"a": 1}
