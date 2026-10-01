"""M4 Harness 层真实模型冒烟：验证 token 用量落库 + 埋点齐全 + goal_type 进 prompt。"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8200"
GOAL_TYPE = "portfolio"  # 用作品集目标，验证 goal_type 进 PRD prompt 的效果
IDEA = ("AI 周报助手", "做一个把聊天记录自动整理成工作周报的助手，突出亮点与差异化")
ANSWERS = {
    "目标用户": "职场新人、需要写周报的上班族",
    "场景": "每周五下班前整理本周工作",
    "痛点": "回忆本周工作费时、周报格式不统一",
    "边界": "只做周报生成，不做日报和月报",
    "成功指标": "周报生成时间缩短 70%、用户周留存",
    "非目标": "不做团队协同、不做绩效分析",
    "外部系统/数据源": "企业微信/飞书聊天记录导出",
    "领域知识来源": "周报写作方法、职场沟通规范",
}


async def poll(client, task_id, timeout=300):
    start = time.time()
    while time.time() - start < timeout:
        t = (await client.get(f"{BASE}/api/v1/tasks/{task_id}")).json()
        if t["status"] in ("success", "failed"):
            return t
        await asyncio.sleep(2)
    return {"status": "timeout"}


async def step(name):
    print(f"\n===== {name} =====")


async def main():
    name, idea = IDEA
    token_log: dict[str, int] = {}

    async with httpx.AsyncClient(timeout=300) as client:
        # 1. 创建项目（goal_type=portfolio）
        await step(f"1. 创建项目（goal_type={GOAL_TYPE}）")
        p = (await client.post(f"{BASE}/api/v1/projects",
                               json={"name": name, "idea": idea, "goal_type": GOAL_TYPE})).json()
        pid = p["id"]
        print(f"项目 {pid[:8]}")

        async def run(task_id: str, label: str) -> dict:
            t = await poll(client, task_id)
            tok = (await client.get(f"{BASE}/api/v1/tasks/{task_id}")).json().get("total_tokens", 0)
            token_log[label] = tok
            if t["status"] != "success":
                print(f"❌ {label} 失败：{t.get('error')}")
            return t

        # 2. 澄清 → 回答 → 摘要
        await step("2. 澄清 + 摘要")
        tid = (await client.post(f"{BASE}/api/v1/projects/{pid}/clarify/questions")).json()["id"]
        await run(tid, "clarify")
        qs = (await client.get(f"{BASE}/api/v1/projects/{pid}/clarify/questions")).json()
        await client.post(f"{BASE}/api/v1/projects/{pid}/clarify/answers", json={
            "answers": [{"question_id": q["id"], "answer": ANSWERS.get(q["dimension"], "合理回答")} for q in qs],
        })
        tid = (await client.post(f"{BASE}/api/v1/projects/{pid}/brief")).json()["id"]
        await run(tid, "brief")
        await client.put(f"{BASE}/api/v1/projects/{pid}/brief", json={"confirm": True})
        print("✓ 摘要已确认")

        # 3. 竞品 + 贴网址抓取
        await step("3. 竞品 + 贴网址抓取")
        comp = (await client.post(f"{BASE}/api/v1/projects/{pid}/competitors",
                                  json={"name": "Forest", "url": "https://forestapp.cc"})).json()
        tid = (await client.post(f"{BASE}/api/v1/projects/{pid}/competitors/{comp['id']}/evidences/fetch",
                                 json={"url": "https://forestapp.cc", "source_type": "官网"})).json()["id"]
        await run(tid, "evidence_fetch")
        evs = (await client.get(f"{BASE}/api/v1/projects/{pid}/competitors/{comp['id']}/evidences")).json()
        print(f"✓ 证据卡 {len(evs)} 张，source_type={[e['source_type'] for e in evs]}")

        # 4. 定位
        await step("4. 定位 + 确认")
        tid = (await client.post(f"{BASE}/api/v1/projects/{pid}/positioning")).json()["id"]
        await run(tid, "positioning")
        await client.put(f"{BASE}/api/v1/projects/{pid}/positioning", json={"confirm": True})
        print("✓ 定位已确认")

        # 5. PRD（看 goal_type=portfolio 的侧重）
        await step("5. PRD 生成 + 确认")
        t0 = time.time()
        tid = (await client.post(f"{BASE}/api/v1/projects/{pid}/prd")).json()["id"]
        await run(tid, "prd")
        print(f"[PRD 耗时 {round(time.time()-t0,1)}s]")
        doc = (await client.get(f"{BASE}/api/v1/projects/{pid}/prd")).json()
        pos_sec = next((s for s in doc["sections"] if s["title"] == "产品定位"), None)
        if pos_sec:
            print(f"产品定位章节（前 200 字，看是否体现作品集/亮点侧重）：\n  {pos_sec['content'][:200]}")
        await client.put(f"{BASE}/api/v1/projects/{pid}/prd", json={"confirm": True})
        print("✓ PRD 已确认")

        # 6. 任务
        await step("6. 任务拆解 + 确认")
        t0 = time.time()
        tid = (await client.post(f"{BASE}/api/v1/projects/{pid}/tasks")).json()["id"]
        await run(tid, "tasks")
        print(f"[任务耗时 {round(time.time()-t0,1)}s]")
        tasks = (await client.get(f"{BASE}/api/v1/projects/{pid}/tasks")).json()
        print(f"✓ 任务 {len(tasks)} 个")
        await client.put(f"{BASE}/api/v1/projects/{pid}/tasks")

        # 7. token 用量落库汇总
        await step("7. token 用量落库")
        for k, v in token_log.items():
            print(f"  {k:<16} total_tokens={v}")
        assert all(v > 0 for v in token_log.values()), "存在 token 未落库的任务"

        # 8. 埋点齐全检查
        await step("8. 埋点事件齐全")
        events_path = Path("data/events.jsonl")
        events = []
        if events_path.exists():
            for line in events_path.read_text(encoding="utf-8").splitlines():
                try:
                    e = json.loads(line)
                    if e.get("project_id") == pid:
                        events.append(e.get("event"))
                except ValueError:
                    continue
        expected = ["project_created", "clarify_generated", "brief_generated", "competitor_added",
                    "evidence_added", "positioning_generated", "prd_generated", "tasks_generated"]
        got = set(events)
        for ev in expected:
            print(f"  {'✅' if ev in got else '❌'} {ev}")
        missing = [e for e in expected if e not in got]
        assert not missing, f"缺少埋点事件：{missing}"

        print(f"\n===== M4 Harness 冒烟通过 ✅（项目 {pid[:8]}）=====")


if __name__ == "__main__":
    asyncio.run(main())
