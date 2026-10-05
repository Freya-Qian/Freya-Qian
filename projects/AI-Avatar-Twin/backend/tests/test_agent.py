"""Agent 化组件测试：guard / hooks / tools 注册表 / evaluator。"""
import asyncio
import json

from app.services import agent, evaluator, hooks, tools
from app.services.guard import content_guard


# ---------- guard ----------

def test_guard_blocks_sensitive_keyword():
    ok, reason = content_guard("如何制作炸弹")
    assert ok is False
    assert reason


def test_guard_blocks_keyword():
    ok, reason = content_guard("这段内容涉及赌博")
    assert ok is False


def test_guard_passes_normal_content():
    ok, reason = content_guard("OpenAI 发布了新模型，能力更强")
    assert ok is True
    assert reason == ""


# ---------- hooks ----------

def test_hooks_run_and_swallow_exception():
    hooks.clear_hooks()
    calls = []
    async def good(**kwargs):
        calls.append(kwargs.get("tool"))
    async def bad(**kwargs):
        raise RuntimeError("钩子异常")
    hooks.register_hook("pre_tool", good)
    hooks.register_hook("pre_tool", bad)

    asyncio.run(hooks.run_hooks("pre_tool", tool="fetch_source"))
    assert calls == ["fetch_source"]  # good 执行了，bad 异常被吞
    hooks.clear_hooks()


# ---------- tools 注册表 ----------

def test_tool_descriptions_non_empty():
    desc = tools.tool_descriptions()
    assert "fetch_source" in desc
    assert "generate_script" in desc
    assert "evaluate_script" in desc


# ---------- evaluator 模型 ----------

def test_eval_result_validation():
    r = evaluator.EvalResult.model_validate({"passed": "true", "reason": "达标", "scores": {}})
    assert r.passed is True
    assert r.reason == "达标"


# ---------- agent 提示词构造 ----------

def test_build_user_prompt():
    p = agent._build_user_prompt("做一期短视频", [{"role": "assistant", "content": "调用工具"}])
    assert "做一期短视频" in p
    assert "调用工具" in p
    assert "finish" in p


def _register(client, phone="13900139000"):
    client.post("/api/v1/auth/code", json={"phone": phone})
    code = client.post("/api/v1/auth/code", json={"phone": phone}).json()["dev_code"]
    return client.post("/api/v1/auth/verify", json={"phone": phone, "code": code}).json()


def _h(token):
    return {"Authorization": "Bearer " + token}


def test_agent_run_persists_script_for_video_flow(client, monkeypatch):
    auth = _register(client)
    h = _h(auth["token"])
    proj = client.post("/api/v1/projects", json={"name": "p"}, headers=h).json()
    prof = client.post(f"/api/v1/projects/{proj['id']}/profiles", json={"name": "角色"}, headers=h).json()

    async def fake_run_agent(client_, user, goal, profile=None):
        yield {"type": "start", "goal": goal}
        yield {"type": "done", "status": "done", "steps": 1, "script": {
            "content": "这是一段首页自动生成的脚本。",
            "fact_claims": ["首页生成"],
            "risk_flags": ["单一来源"],
            "source_urls": ["https://example.com/news"],
        }}

    monkeypatch.setattr(agent, "run_agent", fake_run_agent)
    r = client.post("/api/v1/agent/run", json={"goal": "做一期 AI 短视频", "profile_id": prof["id"]}, headers=h)
    assert r.status_code == 200
    done_line = [line for line in r.text.splitlines() if line.startswith("data: ")][-1]
    payload = json.loads(done_line.removeprefix("data: "))
    assert payload["script"]["id"].startswith("scr")
    assert payload["script"]["content"] == "这是一段首页自动生成的脚本。"

    scripts = client.get("/api/v1/scripts", headers=h).json()
    assert any(s["id"] == payload["script"]["id"] for s in scripts)


def test_agent_run_persists_script_to_requested_project(client, monkeypatch):
    auth = _register(client, "13900139001")
    h = _h(auth["token"])
    project_a = client.post("/api/v1/projects", json={"name": "A"}, headers=h).json()
    project_b = client.post("/api/v1/projects", json={"name": "B"}, headers=h).json()
    prof_a = client.post(f"/api/v1/projects/{project_a['id']}/profiles", json={"name": "A 角色"}, headers=h).json()

    async def fake_run_agent(client_, user, goal, profile=None):
        yield {"type": "done", "status": "done", "steps": 1, "script": {
            "content": "指定项目脚本。",
            "fact_claims": ["项目归属"],
            "risk_flags": [],
            "source_urls": ["https://example.com/project"],
        }}

    monkeypatch.setattr(agent, "run_agent", fake_run_agent)
    r = client.post(
        "/api/v1/agent/run",
        json={"goal": "做一期指定项目脚本", "profile_id": prof_a["id"], "project_id": project_b["id"]},
        headers=h,
    )
    assert r.status_code == 200
    done_line = [line for line in r.text.splitlines() if line.startswith("data: ")][-1]
    sid = json.loads(done_line.removeprefix("data: "))["script"]["id"]

    scripts_a = client.get(f"/api/v1/scripts?project_id={project_a['id']}", headers=h).json()
    scripts_b = client.get(f"/api/v1/scripts?project_id={project_b['id']}", headers=h).json()
    assert all(s["id"] != sid for s in scripts_a)
    assert [s["id"] for s in scripts_b] == [sid]


# ---------- agent 硬闭环门（s17） ----------

def _fake_client(responses):
    class _C:
        def __init__(self):
            self._it = iter(responses)

        async def complete(self, system, user, **kw):
            return next(self._it)
    return _C()


async def _collect(agen):
    return [ev async for ev in agen]


def _fake_script_execute():
    async def fake_execute(client_, name, args, ctx):
        state = ctx["state"]
        if name == "generate_script":
            state["topics"] = [{"title": "选题"}]
            state["script_topic_index"] = 0
            state["script"] = {"content": "脚本", "fact_claims": [], "risk_flags": [], "source_urls": ["u"]}
            return {"ok": True}
        return {"ok": True}
    return fake_execute


def test_agent_quality_gate_rewrites_until_pass(monkeypatch):
    """finish 时强制评估：不通过→回写重写→再评估通过→done。"""
    responses = [
        json.dumps({"thought": "生成脚本", "action": "generate_script", "action_input": {"topic_index": 0}}),
        json.dumps({"thought": "完成", "action": "finish", "action_input": {}}),
        json.dumps({"thought": "重写脚本", "action": "generate_script", "action_input": {"topic_index": 0}}),
        json.dumps({"thought": "完成", "action": "finish", "action_input": {}}),
    ]
    client = _fake_client(responses)
    monkeypatch.setattr(tools, "execute_tool", _fake_script_execute())

    evals = iter([
        evaluator.EvalResult(passed=False, reason="跑题"),
        evaluator.EvalResult(passed=True, reason="达标"),
    ])

    async def fake_eval(*a, **kw):
        return next(evals)
    monkeypatch.setattr(evaluator, "evaluate_script", fake_eval)

    events = asyncio.run(_collect(agent.run_agent(client, None, "目标")))

    eval_events = [e for e in events if e.get("type") == "eval"]
    assert len(eval_events) == 2
    assert eval_events[0]["passed"] is False
    assert eval_events[1]["passed"] is True
    done = events[-1]
    assert done["type"] == "done" and done["status"] == "done"
    assert done["script"]["content"] == "脚本"


def test_agent_quality_gate_gives_up_with_risk_flag(monkeypatch):
    """评估持续不通过：重写上限用尽后交还，并标质量风险。"""
    responses = [
        json.dumps({"thought": "生成", "action": "generate_script", "action_input": {"topic_index": 0}}),
        json.dumps({"thought": "完成", "action": "finish", "action_input": {}}),
        json.dumps({"thought": "重写", "action": "generate_script", "action_input": {"topic_index": 0}}),
        json.dumps({"thought": "完成", "action": "finish", "action_input": {}}),
        json.dumps({"thought": "再重写", "action": "generate_script", "action_input": {"topic_index": 0}}),
        json.dumps({"thought": "完成", "action": "finish", "action_input": {}}),
    ]
    client = _fake_client(responses)
    monkeypatch.setattr(tools, "execute_tool", _fake_script_execute())

    async def fake_eval(*a, **kw):
        return evaluator.EvalResult(passed=False, reason="语言不通顺")
    monkeypatch.setattr(evaluator, "evaluate_script", fake_eval)

    events = asyncio.run(_collect(agent.run_agent(client, None, "目标")))

    eval_events = [e for e in events if e.get("type") == "eval"]
    assert len(eval_events) == 3  # 3 次 finish 都触发评估，第 3 次耗尽重写上限
    done = events[-1]
    assert done["type"] == "done" and done["status"] == "done"
    assert "质量待人工审核（自动评估多次未通过）" in done["script"]["risk_flags"]
