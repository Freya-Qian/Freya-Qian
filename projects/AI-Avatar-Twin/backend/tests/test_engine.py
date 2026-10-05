"""引擎编排单测：脚本流式生成（done / error 收尾）。"""
import asyncio
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.llm import LLMError
from app.models import SourceItem, Topic
from app.services import engine as engine_mod

SCRIPT = {
    "content": "【开头钩子】今天 OpenAI 放大招了。\n【核心事实】发布了新模型。",
    "fact_claims": ["OpenAI 发布新模型"],
    "risk_flags": ["单一来源"],
    "source_urls": ["https://example.com"],
}


class FakeStream:
    def __init__(self, mode="ok"):
        self.mode = mode

    async def stream(self, system, user, max_tokens=2000, temperature=0.6):
        if self.mode == "no_key":
            raise LLMError("NO_API_KEY", "未配置模型 API Key")
        text = json.dumps(SCRIPT, ensure_ascii=False) if self.mode == "ok" else "这不是 JSON"
        for i in range(0, len(text), 10):
            yield text[i : i + 10]


def _make_objs():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = Session()
    src = SourceItem(id="src1", user_id="u1", original_url="https://example.com", title="t", content_text="c", summary="s")
    tpc = Topic(id="t1", user_id="u1", source_item_id="src1", title="t", angle="a", one_liner="o",
                key_facts=["f"], source_urls=["https://example.com"])
    s.add_all([src, tpc])
    s.commit()
    return s, src, tpc


async def _collect(gen):
    out = []
    async for ev in gen:
        out.append(ev)
    return out


def test_stream_ends_with_done():
    _, src, tpc = _make_objs()
    events = asyncio.run(_collect(engine_mod.generate_script_stream(FakeStream("ok"), tpc, src)))
    assert events[-1]["type"] == "done"
    assert events[-1]["script"]["content"]
    assert any(e["type"] == "chunk" for e in events)


def test_stream_no_key_ends_with_error():
    _, src, tpc = _make_objs()
    events = asyncio.run(_collect(engine_mod.generate_script_stream(FakeStream("no_key"), tpc, src)))
    assert events[-1]["type"] == "error"
    assert events[-1]["error"]["code"] == "NO_API_KEY"


def test_stream_bad_json_ends_with_error():
    _, src, tpc = _make_objs()
    events = asyncio.run(_collect(engine_mod.generate_script_stream(FakeStream("bad"), tpc, src)))
    assert events[-1]["type"] == "error"
    assert events[-1]["error"]["code"] == "PARSE_ERROR"


def test_detect_fabrication_appends_flag():
    flags = engine_mod._detect_fabrication("我们实测发现模型会编造 API", ["单一来源"])
    assert "疑似第一人称实测表述（系统无实测能力）" in flags
    assert "单一来源" in flags


def test_detect_fabrication_no_false_positive():
    flags = engine_mod._detect_fabrication("据报道，模型发布了新版本", ["无"])
    assert flags == ["无"]


def test_detect_fabrication_no_duplicate():
    flags = engine_mod._detect_fabrication("我们实测", ["疑似第一人称实测表述（系统无实测能力）"])
    assert flags.count("疑似第一人称实测表述（系统无实测能力）") == 1


def test_detect_single_source_appends_flag():
    flags = engine_mod._detect_single_source(["https://a.com"], [])
    assert flags == ["单一来源"]


def test_detect_single_source_no_flag_when_two_sources():
    flags = engine_mod._detect_single_source(["https://a.com", "https://b.com"], [])
    assert flags == []


def test_detect_single_source_no_duplicate():
    flags = engine_mod._detect_single_source(["https://a.com"], ["单一来源"])
    assert flags.count("单一来源") == 1


def test_truncate_content_within_limit():
    assert engine_mod._truncate_content("短文案。", 30) == "短文案。"


def test_truncate_content_cuts_at_sentence():
    content = "这是一个完整的句子。" * 20  # 很长
    result = engine_mod._truncate_content(content, 30)
    assert len(result) <= 150
    assert result.endswith("。")
