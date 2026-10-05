"""宽容 JSON 解析器单测。"""
import pytest

from app.core.llm import LLMError
from app.services.parser import parse_json


def test_parse_valid():
    assert parse_json('{"a": 1, "b": [1, 2]}') == {"a": 1, "b": [1, 2]}


def test_parse_with_code_fence():
    text = '```json\n{"a": 1}\n```'
    assert parse_json(text) == {"a": 1}


def test_parse_with_trailing_comma():
    assert parse_json('{"a": 1, "b": [1, 2,]}') == {"a": 1, "b": [1, 2]}


def test_parse_with_surrounding_text():
    text = '好的，结果如下：\n{"a": 1}\n希望有帮助。'
    assert parse_json(text) == {"a": 1}


def test_parse_empty_raises():
    with pytest.raises(LLMError) as e:
        parse_json("")
    assert e.value.code == "PARSE_ERROR"


def test_parse_non_json_raises():
    with pytest.raises(LLMError) as e:
        parse_json("这不是 JSON")
    assert e.value.code == "PARSE_ERROR"


def test_parse_list_raises():
    with pytest.raises(LLMError) as e:
        parse_json("[1, 2, 3]")
    assert e.value.code == "PARSE_ERROR"
