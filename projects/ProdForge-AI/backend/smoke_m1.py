"""M1 真实模型冒烟：用真实 Key 走通「想法 → 8 问 → 摘要」链路，输出样例供产品经理打分。

用法：.venv/bin/python smoke_m1.py
不写密钥、不打日志到文件，只打印生成结果（供打分）。
"""
from __future__ import annotations

import asyncio
import sys
import time

import httpx

BASE = "http://127.0.0.1:8200"

IDEAS = [
    ("番茄钟 App", "做一个帮助专注学习的番茄钟 App，支持任务拆分和统计", {
        "目标用户": "在校大学生、考研党、远程办公的自律人群",
        "场景": "自习、居家办公等需要专注的时间段",
        "痛点": "容易分心、任务难以坚持、缺少统计反馈",
        "边界": "只做时间管理和专注统计，不做社交和内容社区",
        "成功指标": "周活跃用户占比、用户平均每日专注时长",
        "非目标": "不做团队协作、不做游戏化社交、不提供内置学习内容",
        "外部系统/数据源": "无外部系统，本地存储即可",
        "领域知识来源": "番茄工作法、时间管理方法论",
    }),
    ("二手书交换平台", "做一个校园二手书交换平台，学生可以发布闲置书并交换", {
        "目标用户": "在校大学生（尤其大二到大四），兼顾研究生",
        "场景": "学期末清书、开学前淘教材、课程调整时换书",
        "痛点": "微信群里信息混乱难找、闲鱼跨城市邮寄慢、线下无信用保障",
        "边界": "只做校园内书换书，不做售卖和物流",
        "成功指标": "周均有效交换单量、48 小时内完成率、用户复用率",
        "非目标": "不做电子书、不接教务系统、不做文具交易",
        "外部系统/数据源": "可选接 ISBN 图书库（如豆瓣 API）识别书目",
        "领域知识来源": "教材适配课程信息、二手交易信用机制",
    }),
    ("AI 周报助手", "做一个把聊天记录自动整理成工作周报的助手", {
        "目标用户": "产品经理、销售、远程协作的工程师等需要写周报的职场人",
        "场景": "周五下午集中整理本周聊天记录生成周报",
        "痛点": "手动整理耗时、容易遗漏关键决策、时间线混乱",
        "边界": "只处理可导入的聊天文本，不做实时监听",
        "成功指标": "单次生成耗时、关键事项提取准确率、无需二次编辑比例",
        "非目标": "不处理语音转文字、不做 PPT、不直接发邮件",
        "外部系统/数据源": "可选对接 IM 导出文件或日历/OKR 系统",
        "领域知识来源": "周报模板规范、汇报写作惯例",
    }),
]


async def poll(client: httpx.AsyncClient, task_id: str, timeout: float = 120) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        r = await client.get(f"{BASE}/api/v1/tasks/{task_id}")
        t = r.json()
        if t["status"] in ("success", "failed"):
            return t
        await asyncio.sleep(1.5)
    return {"status": "timeout"}


async def run_one(client: httpx.AsyncClient, name: str, idea: str, demo_answers: dict) -> dict:
    t0 = time.time()
    r = await client.post(f"{BASE}/api/v1/projects", json={"name": name, "idea": idea, "goal_type": "real"})
    r.raise_for_status()
    pid = r.json()["id"]

    r = await client.post(f"{BASE}/api/v1/projects/{pid}/clarify/questions")
    r.raise_for_status()
    q_task = await poll(client, r.json()["id"])
    q_t = round(time.time() - t0, 1)
    if q_task["status"] != "success":
        return {"name": name, "idea": idea, "error": q_task.get("error", q_task["status"])}

    qs = (await client.get(f"{BASE}/api/v1/projects/{pid}/clarify/questions")).json()

    # 模拟用户回答（每个想法用对应领域的真实回答）
    answers = {q["dimension"]: demo_answers.get(q["dimension"], "按产品想法合理回答") for q in qs}
    await client.post(f"{BASE}/api/v1/projects/{pid}/clarify/answers", json={
        "answers": [{"question_id": q["id"], "answer": answers[q["dimension"]]} for q in qs],
    })

    t1 = time.time()
    r = await client.post(f"{BASE}/api/v1/projects/{pid}/brief")
    r.raise_for_status()
    b_task = await poll(client, r.json()["id"])
    b_t = round(time.time() - t1, 1)
    if b_task["status"] != "success":
        return {"name": name, "idea": idea, "questions": qs, "error": b_task.get("error", b_task["status"])}

    brief = (await client.get(f"{BASE}/api/v1/projects/{pid}/brief")).json()
    return {"name": name, "idea": idea, "questions": qs, "brief": brief,
            "question_seconds": q_t, "brief_seconds": b_t}


def _demo_answer(dim: str, idea: str) -> str:
    # 该函数已不再使用，保留占位避免误引用
    return "按产品想法合理回答"


async def main():
    async with httpx.AsyncClient(timeout=120) as client:
        results = []
        for name, idea, demo_answers in IDEAS:
            print(f"\n===== 样例：{name} =====")
            res = await run_one(client, name, idea, demo_answers)
            results.append(res)
            if "error" in res:
                print(f"[失败] {res['error']}")
                continue
            print(f"[生成 8 问耗时 {res['question_seconds']}s]")
            for q in res["questions"]:
                print(f"  - [{q['dimension']}] {q['question']}")
            print(f"[生成摘要耗时 {res['brief_seconds']}s]")
            b = res["brief"]
            for k in ("one_liner", "target_users", "scenarios", "pains", "goals",
                      "non_goals", "success_metrics", "external_systems", "knowledge_sources", "open_questions"):
                print(f"  · {k}: {b.get(k)}")

    ok = sum(1 for r in results if "error" not in r)
    print(f"\n===== 汇总：{ok}/{len(results)} 个样例跑通 =====")
    if ok != len(results):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
