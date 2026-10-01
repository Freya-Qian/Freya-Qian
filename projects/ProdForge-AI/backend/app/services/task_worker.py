"""异步 LLM 任务后台执行：单进程串行队列，状态先落库再执行，崩溃可恢复。

任务分发采用注册表（TASK_HANDLERS），新增任务类型只需 @register_task 注册，不动核心循环。
"""
from __future__ import annotations

import asyncio
import json
import traceback
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import func

from app.config import TOKEN_PRICE_PER_1K, settings
from app.core.db import SessionLocal
from app.core.llm import LLMClient, LLMError
from app.models import (
    ClarificationQA,
    Competitor,
    CompetitorEvidence,
    DevTask,
    Positioning,
    ProductDoc,
    Project,
    RequirementBrief,
    Task,
)
from app.services import clarify, competitor_service, evidence, fetcher, positioning, prd, tasks
from app.services.observability import record_event
from app.services.prompts import BRIEF_FIELDS

_queue: asyncio.Queue | None = None
_stop_event: asyncio.Event | None = None


def invalidate_downstream(db, project: Project, stage: str) -> None:
    """Preserve content/history while invalidating the latest dependent artifacts."""
    downstream = {
        "clarify": (Positioning, ProductDoc),
        "position": (ProductDoc,),
        "prd": (),
        "tasks": (),
    }
    for model in downstream[stage]:
        latest = db.query(model).filter(model.project_id == project.id).order_by(model.version.desc()).first()
        if latest is not None:
            latest.status = "stale"
    project.current_stage = stage

# 任务类型 → 处理器注册表（s02 工具系统抽象）
TASK_HANDLERS: dict[str, Callable] = {}


def register_task(task_type: str):
    """把处理器注册到 TASK_HANDLERS，process_task 按注册表分发。"""
    def deco(fn):
        TASK_HANDLERS[task_type] = fn
        return fn
    return deco


# 任务类型 → 埋点事件名（对齐 PRD 6.2 漏斗指标采集点）
_EVENT_BY_TYPE = {
    "clarify_questions": "clarify_generated",
    "brief": "brief_generated",
    "positioning": "positioning_generated",
    "evidence_fetch": "evidence_added",
    "prd": "prd_generated",
    "tasks": "tasks_generated",
    "export": "exported",
}


def start_worker() -> None:
    global _queue, _stop_event
    if _queue is None:
        _queue = asyncio.Queue()
        _stop_event = asyncio.Event()
        asyncio.create_task(_worker())


def stop_worker() -> None:
    """优雅关闭：通知 worker 停止接收新任务（当前任务处理完后退出，剩余 queued 标 failed）。"""
    global _stop_event
    if _stop_event is not None:
        _stop_event.set()


def enqueue(task_id: str) -> None:
    assert _queue is not None, "worker 未启动"
    _queue.put_nowait(task_id)


async def _worker() -> None:
    assert _stop_event is not None
    while not _stop_event.is_set():
        try:
            task_id = await asyncio.wait_for(_queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue
        try:
            await process_task(task_id)
        except Exception:
            traceback.print_exc()
        finally:
            _queue.task_done()
    _mark_remaining_failed()


def _mark_remaining_failed() -> None:
    """停机时把仍 queued 的任务标 failed（不自动重做，由用户重试）。"""
    db = SessionLocal()
    try:
        db.query(Task).filter(Task.status == "queued").update(
            {Task.status: "failed", Task.error: "服务关闭导致任务中断，请重试"},
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()


def _project_cost_cny(db, project_id: str) -> float:
    """累计该项目所有已落库 Task 的 total_tokens，按估算单价折算费用。"""
    if not project_id:
        return 0.0
    total = (
        db.query(func.coalesce(func.sum(Task.total_tokens), 0))
        .filter(Task.project_id == project_id)
        .scalar()
    )
    return float(total or 0) * TOKEN_PRICE_PER_1K / 1000


def _check_budget(db, project_id: str) -> None:
    """超预算软护栏（D4）：估算费用达到上限时拦截新任务。"""
    cost = _project_cost_cny(db, project_id)
    if cost >= settings.project_budget_cny:
        raise LLMError(
            "BUDGET_EXCEEDED",
            f"项目 token 预算已用尽（约 {cost:.2f} 元 / 上限 {settings.project_budget_cny} 元），"
            "请调高预算或新建项目",
        )


async def process_task(task_id: str) -> None:
    """处理单个任务（可被测试直接调用）。状态 queued→processing→success/failed。"""
    db = SessionLocal()
    task = None
    try:
        task = db.get(Task, task_id)
        if task is None or task.status != "queued":
            return
        task.status = "processing"
        db.commit()

        client = LLMClient()
        _check_budget(db, task.project_id)  # 超预算拦截（软护栏 D4）

        handler = TASK_HANDLERS.get(task.task_type)
        if handler is None:
            raise LLMError("INVALID_INPUT", f"未知任务类型：{task.task_type}")
        await handler(db, task, client)

        # token 用量落库（P0-2）
        u = client.last_usage or {}
        task.prompt_tokens = u.get("prompt_tokens", 0)
        task.completion_tokens = u.get("completion_tokens", 0)
        task.total_tokens = u.get("total_tokens", 0)
        task.status = "success"
        db.commit()

        # 埋点（P0-3）
        event = _EVENT_BY_TYPE.get(task.task_type)
        if event:
            record_event(event, task.project_id or "", task_id=task.id)
    except Exception as e:
        db.rollback()
        if task is not None:
            task = db.get(Task, task_id)
            if task is not None:
                task.status = "failed"
                task.error = (str(getattr(e, "message", None) or e))[:500]
                db.commit()
    finally:
        db.close()


@register_task("clarify_questions")
async def _process_clarify_questions(db, task: Task, client: LLMClient) -> None:
    project = db.get(Project, task.project_id)
    if project is None:
        raise LLMError("NOT_FOUND", "项目不存在")
    questions = await clarify.generate_questions(client, project.idea)
    # 覆盖本轮问题：先删旧的同轮问题，再写入
    db.query(ClarificationQA).filter(
        ClarificationQA.project_id == project.id,
        ClarificationQA.round_num == 1,
    ).delete(synchronize_session=False)
    for q in questions:
        db.add(ClarificationQA(
            project_id=project.id, round_num=1,
            dimension=q["dimension"], question=q["question"], hint=q["hint"],
        ))
    task.result_json = '{"count": %d}' % len(questions)
    db.commit()


@register_task("brief")
async def _process_brief(db, task: Task, client: LLMClient) -> None:
    project = db.get(Project, task.project_id)
    if project is None:
        raise LLMError("NOT_FOUND", "项目不存在")
    qas = (
        db.query(ClarificationQA)
        .filter(ClarificationQA.project_id == project.id)
        .order_by(ClarificationQA.created_at, ClarificationQA.id)
        .all()
    )
    qa_list = [
        {"dimension": qa.dimension, "question": qa.question, "answer": qa.answer}
        for qa in qas
    ]
    brief = await clarify.generate_brief(client, project.idea, qa_list)

    latest = (
        db.query(RequirementBrief)
        .filter(RequirementBrief.project_id == project.id)
        .order_by(RequirementBrief.version.desc())
        .first()
    )
    next_version = (latest.version + 1) if latest else 1
    db.add(RequirementBrief(project_id=project.id, version=next_version, status="draft", **brief))
    invalidate_downstream(db, project, "clarify")
    project.current_stage = "competitor"
    db.commit()


@register_task("positioning")
async def _process_positioning(db, task: Task, client: LLMClient) -> None:
    project = db.get(Project, task.project_id)
    if project is None:
        raise LLMError("NOT_FOUND", "项目不存在")
    brief = (
        db.query(RequirementBrief)
        .filter(RequirementBrief.project_id == project.id)
        .order_by(RequirementBrief.version.desc())
        .first()
    )
    if brief is None:
        raise LLMError("NOT_READY", "请先完成需求澄清（生成需求摘要）")
    if brief.status != "confirmed":
        raise LLMError("NOT_READY", "请先确认最新需求摘要")

    evidences = (
        db.query(CompetitorEvidence)
        .filter(CompetitorEvidence.project_id == project.id)
        .all()
    )
    if not evidences:
        raise LLMError("NOT_READY", "请先添加竞品证据")
    brief_dict = {field: getattr(brief, field) for field in BRIEF_FIELDS}
    ev_list = [
        {
            "ref_key": e.ref_key,
            "evidence_type": e.evidence_type,
            "structured_claim": e.structured_claim,
            "implication": e.implication,
        }
        for e in evidences
    ]
    result = await positioning.generate_positioning(client, brief_dict, ev_list)

    latest = (
        db.query(Positioning)
        .filter(Positioning.project_id == project.id)
        .order_by(Positioning.version.desc())
        .first()
    )
    next_version = (latest.version + 1) if latest else 1
    invalidate_downstream(db, project, "position")
    db.add(Positioning(
        project_id=project.id, version=next_version, status="draft",
        one_liner=result["one_liner"],
        target_users=result["target_users"],
        value_proposition=result["value_proposition"],
        non_goals=result["non_goals"],
        differentiators=json.dumps(result["differentiators"], ensure_ascii=False),
        comparison=json.dumps(result["comparison"], ensure_ascii=False),
        evidence_refs=json.dumps(result["evidence_refs"], ensure_ascii=False),
    ))

    # 更新证据卡引用状态（used_in 标记"定位"）
    all_refs = set(result["evidence_refs"])
    for d in result["differentiators"]:
        all_refs.update(d["evidence_refs"])
    if all_refs:
        for e in evidences:
            if e.ref_key in all_refs:
                used = [x for x in e.used_in.split(",") if x.strip()] if e.used_in else []
                if "定位" not in used:
                    used.append("定位")
                    e.used_in = ",".join(used)
    db.commit()


@register_task("evidence_fetch")
async def _process_evidence_fetch(db, task: Task, client: LLMClient) -> None:
    """贴网址抓取：抓取网页 → LLM 结构化 → 保存证据卡。"""
    inp = json.loads(task.input_json or "{}")
    competitor_id = inp.get("competitor_id")
    url = inp.get("url")
    source_type = inp.get("source_type") or "公开文章"
    comp = db.get(Competitor, competitor_id)
    if comp is None or comp.project_id != task.project_id:
        raise LLMError("NOT_FOUND", "竞品不存在")
    project = db.get(Project, task.project_id)
    if project is None:
        raise LLMError("NOT_FOUND", "项目不存在")

    fetched = await fetcher.fetch_url(url)
    result = await evidence.generate_evidence(client, comp.name, project.idea, fetched)

    ev = CompetitorEvidence(
        competitor_id=comp.id,
        project_id=task.project_id,
        ref_key=competitor_service.next_ref_key(db, comp.id),
        source_type=source_type,
        source_url=url,
        evidence_type=result["evidence_type"],
        raw_excerpt=result["raw_excerpt"],
        structured_claim=result["structured_claim"],
        implication=result["implication"],
        confidence=result["confidence"],
        fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
    db.add(ev)
    db.commit()
    task.result_json = json.dumps({"evidence_id": ev.id, "ref_key": ev.ref_key}, ensure_ascii=False)


@register_task("competitor_recommend")
async def _process_competitor_recommend(db, task: Task, client: LLMClient) -> None:
    """根据项目想法推荐 2-3 个真实竞品（方案 A：LLM 推荐，不接搜索 API）。"""
    project = db.get(Project, task.project_id)
    if project is None:
        raise LLMError("NOT_FOUND", "项目不存在")
    comps = await competitor_service.recommend_competitors(client, project.idea, project.goal_type)
    task.result_json = json.dumps({"competitors": comps}, ensure_ascii=False)


@register_task("prd")
async def _process_prd(db, task: Task, client: LLMClient) -> None:
    """生成带证据引用的 PRD + 证据引用审计。"""
    project = db.get(Project, task.project_id)
    if project is None:
        raise LLMError("NOT_FOUND", "项目不存在")
    brief = (
        db.query(RequirementBrief)
        .filter(RequirementBrief.project_id == project.id)
        .order_by(RequirementBrief.version.desc())
        .first()
    )
    pos = (
        db.query(Positioning)
        .filter(Positioning.project_id == project.id)
        .order_by(Positioning.version.desc())
        .first()
    )
    if brief is None or pos is None:
        raise LLMError("NOT_READY", "请先完成需求摘要与产品定位")
    if brief.status != "confirmed" or pos.status != "confirmed":
        raise LLMError("NOT_READY", "请先重新生成并确认最新需求摘要与产品定位")
    evidences = (
        db.query(CompetitorEvidence)
        .filter(CompetitorEvidence.project_id == project.id)
        .all()
    )
    if not evidences:
        raise LLMError("NOT_READY", "请先添加竞品证据")

    brief_dict = {f: getattr(brief, f) for f in BRIEF_FIELDS}
    pos_dict = {
        "one_liner": pos.one_liner,
        "target_users": pos.target_users,
        "value_proposition": pos.value_proposition,
        "differentiators": json.loads(pos.differentiators or "[]"),
        "non_goals": pos.non_goals,
    }
    ev_list = [
        {"ref_key": e.ref_key, "evidence_type": e.evidence_type,
         "structured_claim": e.structured_claim, "implication": e.implication}
        for e in evidences
    ]
    # P1-2：goal_type 进 prompt（四种目标生成侧重不同的 PRD）
    result = await prd.generate_prd(client, brief_dict, pos_dict, ev_list, project.goal_type)

    # 无证据结论清单合并进 PRD 正文，用户在 PRD 详情里可见（#3）
    if result.get("unverified"):
        extra = "；以下章节缺少证据支撑（待确认）：" + "、".join(result["unverified"])
        for s in result["sections"]:
            if s["title"] == "风险与待确认问题":
                s["content"] = (s["content"] + extra).strip()
                break

    latest = (
        db.query(ProductDoc)
        .filter(ProductDoc.project_id == project.id)
        .order_by(ProductDoc.version.desc())
        .first()
    )
    next_version = (latest.version + 1) if latest else 1
    invalidate_downstream(db, project, "prd")
    doc = ProductDoc(
        project_id=project.id, doc_type="prd", version=next_version, status="draft",
        sections=json.dumps(result["sections"], ensure_ascii=False),
        evidence_refs=json.dumps(result["evidence_refs"], ensure_ascii=False),
    )
    db.add(doc)
    db.flush()

    # 更新证据卡引用状态（used_in 标记"PRD"）
    all_refs = set(result["evidence_refs"])
    for s in result["sections"]:
        all_refs.update(s["evidence_refs"])
    if all_refs:
        for e in evidences:
            if e.ref_key in all_refs:
                used = [x for x in e.used_in.split(",") if x.strip()] if e.used_in else []
                if "PRD" not in used:
                    used.append("PRD")
                    e.used_in = ",".join(used)
    db.commit()
    task.result_json = json.dumps(
        {"doc_id": doc.id, "unverified": result["unverified"]}, ensure_ascii=False)


@register_task("tasks")
async def _process_tasks(db, task: Task, client: LLMClient) -> None:
    """根据 PRD 拆解研发任务。"""
    project = db.get(Project, task.project_id)
    if project is None:
        raise LLMError("NOT_FOUND", "项目不存在")
    doc = (
        db.query(ProductDoc)
        .filter(ProductDoc.project_id == project.id)
        .order_by(ProductDoc.version.desc())
        .first()
    )
    pos = (
        db.query(Positioning)
        .filter(Positioning.project_id == project.id)
        .order_by(Positioning.version.desc())
        .first()
    )
    if doc is None:
        raise LLMError("NOT_READY", "请先生成 PRD")
    if doc.status != "confirmed":
        raise LLMError("NOT_READY", "请先重新生成并确认最新 PRD")
    evidences = (
        db.query(CompetitorEvidence)
        .filter(CompetitorEvidence.project_id == project.id)
        .all()
    )
    sections = json.loads(doc.sections or "[]")
    pos_dict = {
        "one_liner": pos.one_liner if pos else "",
        "differentiators": json.loads(pos.differentiators or "[]") if pos else [],
    }
    ev_list = [{"ref_key": e.ref_key, "structured_claim": e.structured_claim} for e in evidences]
    result = await tasks.generate_tasks(client, sections, pos_dict, ev_list)

    # 覆盖旧任务：先删旧的再写入
    invalidate_downstream(db, project, "tasks")
    db.query(DevTask).filter(DevTask.project_id == project.id).delete(synchronize_session=False)
    for t in result:
        db.add(DevTask(
            project_id=project.id, module=t["module"], title=t["title"],
            description=t["description"], priority=t["priority"],
            acceptance_criteria=t["acceptance_criteria"],
            dependencies=json.dumps(t["dependencies"], ensure_ascii=False),
            source_refs=json.dumps(t["source_refs"], ensure_ascii=False),
        ))
    db.commit()
    task.result_json = json.dumps({"count": len(result)}, ensure_ascii=False)
