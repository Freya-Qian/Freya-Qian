"""M2 真实模型冒烟：真实 Key 走通「想法 → 8 问 → 摘要 → 定位与差异点」。"""
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


async def poll(client, task_id, timeout=180):
    start = time.time()
    while time.time() - start < timeout:
        t = (await client.get(f"{BASE}/api/v1/tasks/{task_id}")).json()
        if t["status"] in ("success", "failed"):
            return t
        await asyncio.sleep(1.5)
    return {"status": "timeout"}


async def main():
    name, idea = IDEA
    async with httpx.AsyncClient(timeout=180) as client:
        p = (await client.post(f"{BASE}/api/v1/projects",
                               json={"name": name, "idea": idea, "goal_type": "real"})).json()
        pid = p["id"]

        # 8 问 → 回答 → 摘要
        await poll(client, (await client.post(f"{BASE}/api/v1/projects/{pid}/clarify/questions")).json()["id"])
        qs = (await client.get(f"{BASE}/api/v1/projects/{pid}/clarify/questions")).json()
        await client.post(f"{BASE}/api/v1/projects/{pid}/clarify/answers", json={
            "answers": [{"question_id": q["id"], "answer": ANSWERS.get(q["dimension"], "按想法合理回答")} for q in qs],
        })
        await poll(client, (await client.post(f"{BASE}/api/v1/projects/{pid}/brief")).json()["id"])
        await client.put(f"{BASE}/api/v1/projects/{pid}/brief", json={"confirm": True})

        # 竞品证据：添加竞品 + 贴网址抓取（不再有 WorkBuddy）
        comp = (await client.post(f"{BASE}/api/v1/projects/{pid}/competitors",
                                  json={"name": "Forest", "url": "https://forestapp.cc"})).json()
        await poll(client, (await client.post(
            f"{BASE}/api/v1/projects/{pid}/competitors/{comp['id']}/evidences/fetch",
            json={"url": "https://forestapp.cc"})).json()["id"])
        evs = (await client.get(f"{BASE}/api/v1/projects/{pid}/competitors/{comp['id']}/evidences")).json()
        print(f"竞品：{comp['name']}，证据卡 {len(evs)} 张")

        # 定位与差异点
        t0 = time.time()
        task = await poll(client, (await client.post(f"{BASE}/api/v1/projects/{pid}/positioning")).json()["id"])
        print(f"\n[定位生成耗时 {round(time.time()-t0,1)}s，状态 {task['status']}]")
        if task["status"] != "success":
            print("失败：", task.get("error"))
            return

        pos = (await client.get(f"{BASE}/api/v1/projects/{pid}/positioning")).json()
        print("一句话定位：", pos["one_liner"])
        print("目标用户：", pos["target_users"])
        print("核心价值主张：", pos["value_proposition"])
        print("差异化（含证据引用）：")
        for d in pos["differentiators"]:
            print(f"  - {d['point']}  [证据: {','.join(d['evidence_refs'])}]")
        print("对比表：")
        for c in pos["comparison"]:
            comps = "；".join(f"{k}={v}" for k, v in (c.get("competitors") or {}).items())
            print(f"  · {c['dimension']}：{comps}｜我们={c.get('our_product','')}")
        print("不做什么：", pos["non_goals"])
        print("引用证据：", ",".join(pos["evidence_refs"]))


if __name__ == "__main__":
    asyncio.run(main())
