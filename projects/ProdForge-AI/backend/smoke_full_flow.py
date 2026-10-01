"""全链路真实模型冒烟（含 M3 代码评审修复验证点）。

覆盖：状态机（先确认定位/PRD）→ 贴网址抓取 source_type 透传 → PRD 无证据清单可见 → 任务编辑/删除 → 确认任务。
"""
from __future__ import annotations

import asyncio
import time

import httpx

BASE = "http://127.0.0.1:8200"
IDEA = ("番茄钟 App", "做一个帮助专注学习的番茄钟 App，支持任务拆分和统计")
ANSWERS = {
    "目标用户": "在校大学生、考研党、远程办公的自律人群",
    "场景": "自习、居家办公等需要专注的时间段",
    "痛点": "容易分心、任务难以坚持、缺少统计反馈",
    "边界": "只做时间管理和专注统计，不做社交和内容社区",
    "成功指标": "周活跃用户占比、用户平均每日专注时长",
    "非目标": "不做团队协作、不做游戏化社交",
    "外部系统/数据源": "无外部系统，本地存储",
    "领域知识来源": "番茄工作法、时间管理方法论",
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
    async with httpx.AsyncClient(timeout=300) as client:
        # 1. 创建项目
        await step("1. 创建项目")
        p = (await client.post(f"{BASE}/api/v1/projects",
                               json={"name": name, "idea": idea, "goal_type": "real"})).json()
        pid = p["id"]
        print(f"项目 {pid[:8]} 已创建，初始阶段 {p['current_stage']}")

        # 2. 澄清 → 回答 → 摘要 → 确认
        await step("2. 需求澄清 + 摘要")
        await poll(client, (await client.post(f"{BASE}/api/v1/projects/{pid}/clarify/questions")).json()["id"])
        qs = (await client.get(f"{BASE}/api/v1/projects/{pid}/clarify/questions")).json()
        await client.post(f"{BASE}/api/v1/projects/{pid}/clarify/answers", json={
            "answers": [{"question_id": q["id"], "answer": ANSWERS.get(q["dimension"], "按想法合理回答")} for q in qs],
        })
        await poll(client, (await client.post(f"{BASE}/api/v1/projects/{pid}/brief")).json()["id"])
        await client.put(f"{BASE}/api/v1/projects/{pid}/brief", json={"confirm": True})
        print("✓ 摘要已确认，进入竞品阶段")

        # 3. 竞品 + 贴网址抓取（验证 source_type 透传 #9）
        await step("3. 竞品 + 贴网址抓取（source_type 透传）")
        comp = (await client.post(f"{BASE}/api/v1/projects/{pid}/competitors",
                                  json={"name": "Forest", "url": "https://forestapp.cc"})).json()
        await poll(client, (await client.post(
            f"{BASE}/api/v1/projects/{pid}/competitors/{comp['id']}/evidences/fetch",
            json={"url": "https://forestapp.cc", "source_type": "官网"})).json()["id"])
        evs = (await client.get(f"{BASE}/api/v1/projects/{pid}/competitors/{comp['id']}/evidences")).json()
        stypes = [e["source_type"] for e in evs]
        print(f"✓ 证据卡 {len(evs)} 张，source_type={stypes}（预期含「官网」，非硬编码「公开文章」）")
        assert any(s == "官网" for s in stypes), "source_type 透传失败"

        # 4. 定位 → 确认（状态机 #1）
        await step("4. 定位 + 确认")
        await poll(client, (await client.post(f"{BASE}/api/v1/projects/{pid}/positioning")).json()["id"])
        await client.put(f"{BASE}/api/v1/projects/{pid}/positioning", json={"confirm": True})
        print("✓ 定位已确认")

        # 5. PRD → 检查无证据清单可见（#3）→ 确认
        await step("5. PRD 生成 + 无证据清单检查 + 确认")
        t0 = time.time()
        t = await poll(client, (await client.post(f"{BASE}/api/v1/projects/{pid}/prd")).json()["id"])
        print(f"[PRD 耗时 {round(time.time()-t0,1)}s，状态 {t['status']}]")
        if t["status"] != "success":
            print("❌ PRD 失败：", t.get("error"))
            return
        doc = (await client.get(f"{BASE}/api/v1/projects/{pid}/prd")).json()
        print(f"PRD 版本 {doc['version']}，章节 {len(doc['sections'])} 个，引用证据 {doc['evidence_refs']}")
        unverified_titles = [s["title"] for s in doc["sections"] if s["status"] == "待确认"]
        print(f"待确认章节：{unverified_titles or '无（全部有证据）'}")
        risk = next((s for s in doc["sections"] if s["title"] == "风险与待确认问题"), None)
        merged = "缺少证据支撑" in (risk["content"] if risk else "")
        print(f"「风险与待确认问题」章节含『缺少证据支撑』清单：{merged}")
        if unverified_titles:
            assert merged, "#3 无证据清单未合并进正文"
        await client.put(f"{BASE}/api/v1/projects/{pid}/prd", json={"confirm": True})
        print("✓ PRD 已确认，进入任务拆解阶段")

        # 6. 任务 → 编辑/删除（#5）→ 确认（#7）
        await step("6. 任务拆解 + 编辑/删除 + 确认")
        t0 = time.time()
        t = await poll(client, (await client.post(f"{BASE}/api/v1/projects/{pid}/tasks")).json()["id"])
        print(f"[任务耗时 {round(time.time()-t0,1)}s，状态 {t['status']}]")
        if t["status"] != "success":
            print("❌ 任务失败：", t.get("error"))
            return
        tasks = (await client.get(f"{BASE}/api/v1/projects/{pid}/tasks")).json()
        p0 = sum(1 for x in tasks if x["priority"] == "P0")
        print(f"任务 {len(tasks)} 个（P0 {p0} 个）")

        # 编辑第一个任务
        first = tasks[0]
        r = (await client.patch(f"{BASE}/api/v1/projects/{pid}/tasks/{first['id']}",
                                json={"title": first["title"] + "（冒烟已编辑）"})).json()
        print(f"✓ 编辑任务成功：{r['title'][:50]}")

        # 删除一个非 P0 任务（保持 ≥5 且 P0 以通过确认校验）
        to_delete = next((x for x in tasks if x["priority"] != "P0"), None)
        if to_delete:
            await client.delete(f"{BASE}/api/v1/projects/{pid}/tasks/{to_delete['id']}")
            after = (await client.get(f"{BASE}/api/v1/projects/{pid}/tasks")).json()
            print(f"✓ 删除任务「{to_delete['title'][:30]}」后剩 {len(after)} 个")

        # 确认任务
        r = await client.put(f"{BASE}/api/v1/projects/{pid}/tasks")
        print(f"✓ 确认任务 → current_stage={r.json()['current_stage']}")

        print(f"\n===== 全链路冒烟通过 ✅（项目 {pid[:8]}）=====")


if __name__ == "__main__":
    asyncio.run(main())
