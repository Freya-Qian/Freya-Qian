"""M3 真实模型冒烟：真实 Key 走通「想法 → 摘要 → 定位 → PRD → 任务拆解」。"""
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


async def poll(client, task_id, timeout=240):
    start = time.time()
    while time.time() - start < timeout:
        t = (await client.get(f"{BASE}/api/v1/tasks/{task_id}")).json()
        if t["status"] in ("success", "failed"):
            return t
        await asyncio.sleep(2)
    return {"status": "timeout"}


async def main():
    name, idea = IDEA
    async with httpx.AsyncClient(timeout=240) as client:
        p = (await client.post(f"{BASE}/api/v1/projects",
                               json={"name": name, "idea": idea, "goal_type": "real"})).json()
        pid = p["id"]

        await poll(client, (await client.post(f"{BASE}/api/v1/projects/{pid}/clarify/questions")).json()["id"])
        qs = (await client.get(f"{BASE}/api/v1/projects/{pid}/clarify/questions")).json()
        await client.post(f"{BASE}/api/v1/projects/{pid}/clarify/answers", json={
            "answers": [{"question_id": q["id"], "answer": ANSWERS.get(q["dimension"], "按想法合理回答")} for q in qs],
        })
        await poll(client, (await client.post(f"{BASE}/api/v1/projects/{pid}/brief")).json()["id"])
        await client.put(f"{BASE}/api/v1/projects/{pid}/brief", json={"confirm": True})
        comp = (await client.post(f"{BASE}/api/v1/projects/{pid}/competitors",
                                  json={"name": "Forest", "url": "https://forestapp.cc"})).json()
        await poll(client, (await client.post(
            f"{BASE}/api/v1/projects/{pid}/competitors/{comp['id']}/evidences/fetch",
            json={"url": "https://forestapp.cc"})).json()["id"])
        await poll(client, (await client.post(f"{BASE}/api/v1/projects/{pid}/positioning")).json()["id"])

        # PRD
        t0 = time.time()
        t = await poll(client, (await client.post(f"{BASE}/api/v1/projects/{pid}/prd")).json()["id"])
        print(f"[PRD 生成耗时 {round(time.time()-t0,1)}s，状态 {t['status']}]")
        if t["status"] != "success":
            print("PRD 失败：", t.get("error"))
            return
        doc = (await client.get(f"{BASE}/api/v1/projects/{pid}/prd")).json()
        print(f"PRD 版本 {doc['version']}，章节 {len(doc['sections'])} 个，引用证据 {doc['evidence_refs']}")
        for s in doc["sections"]:
            flag = " ⚠️待确认" if s["status"] == "待确认" else ""
            refs = ",".join(s["evidence_refs"]) or "无"
            print(f"  [{s['title']}]{flag} 证据:{refs}")
        # 打印两章内容样例
        for s in doc["sections"][:2]:
            print(f"\n--- {s['title']} ---\n{s['content'][:300]}")

        # 任务拆解
        t0 = time.time()
        t = await poll(client, (await client.post(f"{BASE}/api/v1/projects/{pid}/tasks")).json()["id"])
        print(f"\n[任务拆解耗时 {round(time.time()-t0,1)}s，状态 {t['status']}]")
        if t["status"] != "success":
            print("任务失败：", t.get("error"))
            return
        tasks = (await client.get(f"{BASE}/api/v1/projects/{pid}/tasks")).json()
        print(f"任务 {len(tasks)} 个：")
        for t in tasks:
            print(f"  [{t['priority']}/{t['module']}] {t['title']}（验收：{t['acceptance_criteria'][:50]}）")


if __name__ == "__main__":
    asyncio.run(main())
