"""API 路由（MVP 用 /api/v1 集中定义）。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import DEFAULT_USER_ID, save_model_config, settings
from app.core.db import get_db
from app.core.llm import LLMError
from app.models import (
    ClarificationQA,
    Competitor,
    CompetitorEvidence,
    DecisionLog,
    DevTask,
    Export,
    Feedback,
    Positioning,
    ProductDoc,
    Project,
    RequirementBrief,
    Task,
)
from app.schemas import (
    GOAL_TYPES,
    SAMPLE_IDEAS,
    AnswersIn,
    BriefOut,
    BriefUpdate,
    CompetitorCreate,
    CompetitorOut,
    DecisionLogOut,
    DevTaskOut,
    DevTaskUpdate,
    EvidenceCreate,
    EvidenceFetchIn,
    EvidenceOut,
    EvidenceUpdate,
    ExportCreate,
    ExportResult,
    FeedbackCreate,
    FeedbackOut,
    ModelSettingsUpdate,
    PositioningOut,
    PositioningUpdate,
    PrdOut,
    PrdUpdate,
    ProjectCreate,
    ProjectOut,
    QuestionOut,
    TaskOut,
)
from app.services import competitor_service, export_service, fetcher, prd, task_worker
from app.services.observability import record_event
from app.services.prompts import (
    CONFIDENCE_LEVELS,
    EVIDENCE_TYPES,
    KEY_DIMENSIONS,
    SOURCE_TYPES,
    TASK_MODULES,
)

router = APIRouter(prefix="/api/v1")


# ── 设置（模型配置，阶段 3 配套，热生效无需重启）──

@router.get("/settings/model")
def get_model_settings():
    """返回模型配置。Key 只回显尾 4 位，绝不回传完整 Key。"""
    key = settings.model_api_key or ""
    return {
        "configured": bool(key),
        "model_api_key": key[-4:] if len(key) >= 4 else "",
        "model_name": settings.model_name,
        "model_base_url": settings.model_base_url,
    }


@router.put("/settings/model")
def update_model_settings(payload: ModelSettingsUpdate):
    """保存模型配置：写 .env + 热更新（无需重启）。"""
    if not payload.model_api_key.strip():
        raise LLMError("INVALID_INPUT", "API Key 不能为空")
    save_model_config(
        payload.model_api_key,
        model_name=payload.model_name,
        model_base_url=payload.model_base_url,
    )
    return get_model_settings()


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        # SQLite write lock makes the active-task check and cleanup atomic.
        db.execute(text("BEGIN IMMEDIATE"))
        project = _require_project(db, project_id)
        active = db.query(Task.id).filter(
            Task.project_id == project_id,
            Task.status.in_(["queued", "processing"]),
        ).first()
        if active is not None:
            raise LLMError("CONFLICT", "项目有排队或运行中的任务，请等待任务结束后再删除")

        # Evidence references competitors; remove it before its parent rows.
        for model in (
            CompetitorEvidence, ClarificationQA, RequirementBrief, ProductDoc,
            DevTask, Positioning, DecisionLog, Feedback, Export, Task, Competitor,
        ):
            db.query(model).filter(model.project_id == project_id).delete(
                synchronize_session=False,
            )
        db.delete(project)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"deleted": project_id}


@router.get("/samples")
def list_samples():
    """冷启动示例想法（PRD 5.3）。"""
    return {"samples": SAMPLE_IDEAS, "goal_types": GOAL_TYPES}


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    if payload.goal_type not in GOAL_TYPES:
        raise LLMError("INVALID_INPUT", "goal_type 不合法，可选：course/portfolio/real/team_review")
    project = Project(
        user_id=DEFAULT_USER_ID,
        name=payload.name.strip(),
        idea=payload.idea.strip(),
        goal_type=payload.goal_type,
        current_stage="clarify",
        status="active",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    record_event("project_created", project.id)
    return project


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return (
        db.query(Project)
        .filter(Project.user_id == DEFAULT_USER_ID)
        .order_by(Project.updated_at.desc())
        .all()
    )


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None or project.user_id != DEFAULT_USER_ID:
        raise LLMError("NOT_FOUND", "项目不存在")
    return project


@router.post("/projects/{project_id}/clarify/questions", response_model=TaskOut, status_code=202)
def start_clarify_questions(project_id: str, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    if _active_task(db, project.id, "clarify_questions"):
        raise LLMError("CONFLICT", "已有进行中的澄清问题生成任务，请等待完成或刷新")
    task = Task(project_id=project.id, task_type="clarify_questions", status="queued")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_worker.enqueue(task.id)
    return task


@router.get("/projects/{project_id}/clarify/questions", response_model=list[QuestionOut])
def list_clarify_questions(project_id: str, db: Session = Depends(get_db)):
    _require_project(db, project_id)
    return [
        _question_out(qa)
        for qa in db.query(ClarificationQA)
        .filter(ClarificationQA.project_id == project_id)
        .order_by(ClarificationQA.created_at, ClarificationQA.id)
        .all()
    ]


@router.post("/projects/{project_id}/clarify/answers", response_model=list[QuestionOut])
def submit_clarify_answers(project_id: str, payload: AnswersIn, db: Session = Depends(get_db)):
    _require_project(db, project_id)
    qas = db.query(ClarificationQA).filter(ClarificationQA.project_id == project_id).all()
    by_id = {qa.id: qa for qa in qas}
    for item in payload.answers:
        qa = by_id.get(item.question_id)
        if qa is None:
            raise LLMError("INVALID_INPUT", f"问题不存在：{item.question_id}")
        answer = item.answer.strip()
        qa.answer = answer
        qa.skipped = not answer
    db.commit()
    return [
        _question_out(qa)
        for qa in db.query(ClarificationQA)
        .filter(ClarificationQA.project_id == project_id)
        .order_by(ClarificationQA.created_at, ClarificationQA.id)
        .all()
    ]


@router.post("/projects/{project_id}/brief", response_model=TaskOut, status_code=202)
def start_brief(project_id: str, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    if _active_task(db, project.id, "brief"):
        raise LLMError("CONFLICT", "已有进行中的需求摘要生成任务，请等待完成或刷新")
    missing = _missing_key_items(db, project.id)
    if missing:
        raise LLMError("INVALID_INPUT", "必答项未填：" + "、".join(missing) + "（其余 5 个选答项可跳过）")
    _require_workflow_idle(db, project.id)
    task_worker.invalidate_downstream(db, project, "clarify")
    task = Task(project_id=project.id, task_type="brief", status="queued")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_worker.enqueue(task.id)
    return task


@router.get("/projects/{project_id}/brief", response_model=BriefOut)
def get_brief(project_id: str, db: Session = Depends(get_db)):
    _require_project(db, project_id)
    brief = (
        db.query(RequirementBrief)
        .filter(RequirementBrief.project_id == project_id)
        .order_by(RequirementBrief.version.desc())
        .first()
    )
    if brief is None:
        raise LLMError("NOT_FOUND", "尚未生成需求摘要")
    return brief


@router.put("/projects/{project_id}/brief", response_model=BriefOut)
def update_brief(project_id: str, payload: BriefUpdate, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    _require_workflow_idle(db, project.id)
    brief = (
        db.query(RequirementBrief)
        .filter(RequirementBrief.project_id == project_id)
        .order_by(RequirementBrief.version.desc())
        .first()
    )
    if brief is None:
        raise LLMError("NOT_FOUND", "尚未生成需求摘要")
    data = payload.model_dump(exclude_unset=True)
    if any(getattr(brief, key) != value for key, value in data.items() if key != "confirm"):
        _invalidate_from(db, project, "clarify")
    for field in ("one_liner", "target_users", "scenarios", "pains", "goals",
                  "non_goals", "success_metrics", "external_systems",
                  "knowledge_sources", "open_questions"):
        if field in data:
            setattr(brief, field, data[field])
    if data.get("confirm"):
        if brief.status != "confirmed":
            task_worker.invalidate_downstream(db, project, "clarify")
        brief.status = "confirmed"
        _advance_stage(project, "competitor")
        _log_decision(db, project.id, "需求摘要已确认，进入竞品证据阶段",
                      reason="用户确认需求摘要", source="阶段确认")
    db.commit()
    db.refresh(brief)
    return brief


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None or task.project_id is None:
        raise LLMError("NOT_FOUND", "任务不存在")
    _require_project(db, task.project_id)
    return task


# ── M2 竞品证据与定位 ──

@router.get("/projects/{project_id}/competitors", response_model=list[CompetitorOut])
def list_competitors(project_id: str, db: Session = Depends(get_db)):
    _require_project(db, project_id)
    return db.query(Competitor).filter(Competitor.project_id == project_id).all()


@router.post("/projects/{project_id}/competitors", response_model=CompetitorOut, status_code=201)
def add_competitor(project_id: str, payload: CompetitorCreate, db: Session = Depends(get_db)):
    _require_project(db, project_id)
    count = db.query(Competitor).filter(Competitor.project_id == project_id).count()
    if count >= competitor_service.MAX_COMPETITORS:
        raise LLMError("CONFLICT", f"最多添加 {competitor_service.MAX_COMPETITORS} 个竞品")
    comp = Competitor(project_id=project_id, **payload.model_dump())
    db.add(comp)
    db.commit()
    db.refresh(comp)
    record_event("competitor_added", project_id)
    return comp


@router.delete("/projects/{project_id}/competitors/{competitor_id}")
def delete_competitor(project_id: str, competitor_id: str,
                      db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        comp = _require_competitor(db, project_id, competitor_id)
        if comp.user_id != DEFAULT_USER_ID:
            raise LLMError("NOT_FOUND", "竞品不存在")
        if db.query(Task.id).filter(
            Task.project_id == project_id, Task.status.in_(["queued", "processing"]),
        ).first() is not None:
            raise LLMError("CONFLICT", "项目有排队或运行中的任务，请等待任务结束后再删除")
        evidences = db.query(CompetitorEvidence).filter(
            CompetitorEvidence.competitor_id == competitor_id,
        ).all()
        _require_unreferenced_evidence(db, project_id, {ev.ref_key for ev in evidences})
        db.query(CompetitorEvidence).filter(
            CompetitorEvidence.competitor_id == competitor_id,
        ).delete(synchronize_session=False)
        project = _require_project(db, project_id)
        if project.default_competitor_id == competitor_id:
            project.default_competitor_id = None
        db.delete(comp)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"deleted": competitor_id}


@router.post("/projects/{project_id}/competitors/{competitor_id}/detach-references")
def detach_competitor_references(project_id: str, competitor_id: str,
                                 allow_shared_refs: bool = False, db: Session = Depends(get_db)):
    """Explicitly remove reference metadata, preserving all documents and prose.

    Legacy E-keys can identify multiple competitors. Shared keys require the
    caller to explicitly accept detaching every occurrence within this project.
    """
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        comp = _require_competitor(db, project_id, competitor_id)
        if comp.user_id != DEFAULT_USER_ID:
            raise LLMError("NOT_FOUND", "竞品不存在")
        _require_workflow_idle(db, project_id)
        keys = {ev.ref_key for ev in db.query(CompetitorEvidence).filter(
            CompetitorEvidence.competitor_id == competitor_id,
        ).all()}
        shared = {ev.ref_key for ev in db.query(CompetitorEvidence).filter(
            CompetitorEvidence.project_id == project_id,
            CompetitorEvidence.competitor_id != competitor_id,
            CompetitorEvidence.ref_key.in_(keys),
        ).all()}
        if shared and not allow_shared_refs:
            raise LLMError("CONFLICT", "引用键被多个竞品共用：" + ", ".join(sorted(shared))
                           + "；仅在接受解除本项目所有同名引用后，使用 allow_shared_refs=true 重试；正文不会删除")
        affected = {}
        for model, fields in (
            (Positioning, ("evidence_refs", "differentiators")),
            (ProductDoc, ("evidence_refs", "sections")),
            (DevTask, ("source_refs",)),
            (DecisionLog, ("evidence_refs",)),
        ):
            changed_rows = 0
            for row in db.query(model).filter(model.project_id == project_id).all() if keys else []:
                changed = False
                for field in fields:
                    try:
                        data = json.loads(getattr(row, field) or "[]")
                    except ValueError as exc:
                        raise LLMError("CONFLICT", "引用数据格式异常，未解除任何引用，请先修复数据") from exc
                    if field in ("differentiators", "sections"):
                        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                            raise LLMError("CONFLICT", "引用数据格式异常，未解除任何引用，请先修复数据")
                        field_changed = False
                        for item in data:
                            refs = item.get("evidence_refs") or []
                            remaining = _without_refs(refs, keys)
                            if remaining != refs:
                                item["evidence_refs"] = remaining
                                field_changed = True
                    else:
                        remaining = _without_refs(data, keys)
                        field_changed = remaining != data
                        data = remaining
                    if field_changed:
                        setattr(row, field, json.dumps(data, ensure_ascii=False))
                        changed = True
                changed_rows += int(changed)
            affected[model.__tablename__] = changed_rows
        if any(affected.values()):
            project = _require_project(db, project_id)
            task_worker.invalidate_downstream(db, project, "clarify")
            brief = db.query(RequirementBrief).filter(RequirementBrief.project_id == project_id).order_by(
                RequirementBrief.version.desc()).first()
            if brief is not None and brief.status == "confirmed":
                project.current_stage = "position"
            _log_decision(db, project_id, "用户解除竞品证据引用，保留正文并重新检查下游产物",
                          reason=f"competitor={competitor_id}; keys={','.join(sorted(keys))}; shared={','.join(sorted(shared))}",
                          source="解除引用")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"competitor_id": competitor_id, "detached_refs": sorted(keys),
            "shared_refs": sorted(shared), "affected": affected,
            "next_action": f"DELETE /api/v1/projects/{project_id}/competitors/{competitor_id}"}


@router.post("/projects/{project_id}/competitors/recommend", response_model=TaskOut, status_code=202)
def recommend_competitors(project_id: str, db: Session = Depends(get_db)):
    """自动推荐竞品（方案 A：LLM 推荐，不接搜索 API）。结果在任务 result_json 的 competitors 字段。"""
    project = _require_project(db, project_id)
    count = db.query(Competitor).filter(Competitor.project_id == project_id).count()
    if count >= competitor_service.MAX_COMPETITORS:
        raise LLMError("CONFLICT", f"竞品已满（最多 {competitor_service.MAX_COMPETITORS} 个），无法推荐")
    if _active_task(db, project.id, "competitor_recommend"):
        raise LLMError("CONFLICT", "已有进行中的竞品推荐任务，请等待完成或刷新")
    task = Task(project_id=project.id, task_type="competitor_recommend", status="queued")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_worker.enqueue(task.id)
    return task


@router.get("/projects/{project_id}/competitors/{competitor_id}/evidences", response_model=list[EvidenceOut])
def list_evidences(project_id: str, competitor_id: str, db: Session = Depends(get_db)):
    _require_competitor(db, project_id, competitor_id)
    return (
        db.query(CompetitorEvidence)
        .filter(CompetitorEvidence.competitor_id == competitor_id)
        .order_by(CompetitorEvidence.created_at, CompetitorEvidence.id)
        .all()
    )


@router.post("/projects/{project_id}/competitors/{competitor_id}/evidences",
             response_model=EvidenceOut, status_code=201)
def add_evidence(project_id: str, competitor_id: str, payload: EvidenceCreate,
                 db: Session = Depends(get_db)):
    comp = _require_competitor(db, project_id, competitor_id)
    url = competitor_service.validate_source_url(payload.source_url)
    if payload.evidence_type not in EVIDENCE_TYPES:
        raise LLMError("INVALID_INPUT", "evidence_type 不合法：" + "/".join(EVIDENCE_TYPES))
    if payload.confidence not in CONFIDENCE_LEVELS:
        raise LLMError("INVALID_INPUT", "confidence 不合法：" + "/".join(CONFIDENCE_LEVELS))
    if payload.source_type not in SOURCE_TYPES:
        raise LLMError("INVALID_INPUT", "source_type 不合法：" + "/".join(SOURCE_TYPES))
    ev = CompetitorEvidence(
        competitor_id=comp.id,
        project_id=project_id,
        ref_key=competitor_service.next_ref_key(db, comp.id),
        source_type=payload.source_type,
        source_url=url,
        evidence_type=payload.evidence_type,
        raw_excerpt=payload.raw_excerpt,
        structured_claim=payload.structured_claim,
        implication=payload.implication,
        confidence=payload.confidence,
        fetched_at=payload.fetched_at,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    record_event("evidence_added", project_id)
    return ev


@router.post("/projects/{project_id}/competitors/{competitor_id}/evidences/fetch",
             response_model=TaskOut, status_code=202)
def fetch_evidence(project_id: str, competitor_id: str, payload: EvidenceFetchIn,
                   db: Session = Depends(get_db)):
    """贴网址抓取：抓取网页 + 生成证据卡（异步）。"""
    comp = _require_competitor(db, project_id, competitor_id)
    url = fetcher.validate_url(payload.url)  # 提前校验，快速失败
    if payload.source_type not in SOURCE_TYPES:
        raise LLMError("INVALID_INPUT", "source_type 不合法：" + "/".join(SOURCE_TYPES))
    task = Task(
        project_id=project_id,
        task_type="evidence_fetch",
        status="queued",
        input_json=json.dumps({"competitor_id": comp.id, "url": url, "source_type": payload.source_type}),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    task_worker.enqueue(task.id)
    return task


@router.patch("/projects/{project_id}/competitors/{competitor_id}/evidences/{evidence_id}",
              response_model=EvidenceOut)
def update_evidence(project_id: str, competitor_id: str, evidence_id: str,
                    payload: EvidenceUpdate, db: Session = Depends(get_db)):
    _require_competitor(db, project_id, competitor_id)
    ev = db.get(CompetitorEvidence, evidence_id)
    if ev is None or ev.competitor_id != competitor_id:
        raise LLMError("NOT_FOUND", "证据卡不存在")
    data = payload.model_dump(exclude_unset=True)
    if data.get("source_url") is not None:
        data["source_url"] = competitor_service.validate_source_url(data["source_url"])
    if data.get("evidence_type") is not None and data["evidence_type"] not in EVIDENCE_TYPES:
        raise LLMError("INVALID_INPUT", "evidence_type 不合法：" + "/".join(EVIDENCE_TYPES))
    if data.get("confidence") is not None and data["confidence"] not in CONFIDENCE_LEVELS:
        raise LLMError("INVALID_INPUT", "confidence 不合法：" + "/".join(CONFIDENCE_LEVELS))
    if data.get("source_type") is not None and data["source_type"] not in SOURCE_TYPES:
        raise LLMError("INVALID_INPUT", "source_type 不合法：" + "/".join(SOURCE_TYPES))
    for k, v in data.items():
        setattr(ev, k, v)
    db.commit()
    db.refresh(ev)
    return ev


@router.delete("/projects/{project_id}/competitors/{competitor_id}/evidences/{evidence_id}",
               status_code=204)
def delete_evidence(project_id: str, competitor_id: str, evidence_id: str,
                    db: Session = Depends(get_db)):
    _require_competitor(db, project_id, competitor_id)
    ev = db.get(CompetitorEvidence, evidence_id)
    if ev is None or ev.competitor_id != competitor_id:
        raise LLMError("NOT_FOUND", "证据卡不存在")
    _require_unreferenced_evidence(db, project_id, {ev.ref_key})
    db.delete(ev)
    db.commit()
    return None


@router.post("/projects/{project_id}/positioning", response_model=TaskOut, status_code=202)
def start_positioning(project_id: str, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    brief = (
        db.query(RequirementBrief)
        .filter(RequirementBrief.project_id == project_id)
        .order_by(RequirementBrief.version.desc())
        .first()
    )
    if brief is None or brief.status != "confirmed":
        raise LLMError("NOT_READY", "请先完成并确认需求摘要（第 3 步）")
    if db.query(Competitor).filter(Competitor.project_id == project_id).count() == 0:
        raise LLMError("NOT_READY", "请先添加竞品")
    if db.query(CompetitorEvidence.id).filter(CompetitorEvidence.project_id == project_id).first() is None:
        raise LLMError("NOT_READY", "请先为竞品抓取网页或手动添加至少一张证据卡，再生成定位")
    if _active_task(db, project.id, "positioning"):
        raise LLMError("CONFLICT", "已有进行中的定位生成任务，请等待完成或刷新")
    _require_workflow_idle(db, project.id)
    task_worker.invalidate_downstream(db, project, "position")
    task = Task(project_id=project.id, task_type="positioning", status="queued")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_worker.enqueue(task.id)
    return task


@router.get("/projects/{project_id}/positioning", response_model=PositioningOut)
def get_positioning(project_id: str, db: Session = Depends(get_db)):
    _require_project(db, project_id)
    p = (
        db.query(Positioning)
        .filter(Positioning.project_id == project_id)
        .order_by(Positioning.version.desc())
        .first()
    )
    if p is None:
        raise LLMError("NOT_FOUND", "尚未生成定位")
    return _positioning_out(p)


@router.put("/projects/{project_id}/positioning", response_model=PositioningOut)
def update_positioning(project_id: str, payload: PositioningUpdate, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    _require_workflow_idle(db, project.id)
    _require_confirmed(db, project.id, RequirementBrief, "需求摘要")
    p = (
        db.query(Positioning)
        .filter(Positioning.project_id == project_id)
        .order_by(Positioning.version.desc())
        .first()
    )
    if p is None:
        raise LLMError("NOT_FOUND", "尚未生成定位")
    data = payload.model_dump(exclude_unset=True)
    if p.status == "stale" and data.get("confirm"):
        raise LLMError("NOT_READY", "需求或证据已更新，请重新生成定位后再确认")
    if any(getattr(p, key) != value for key, value in data.items() if key != "confirm"):
        _invalidate_from(db, project, "position")
    for field in ("one_liner", "target_users", "value_proposition", "non_goals"):
        if field in data:
            setattr(p, field, data[field])
    if data.get("confirm"):
        if p.status != "confirmed":
            task_worker.invalidate_downstream(db, project, "position")
        p.status = "confirmed"
        _advance_stage(project, "prd")
        _log_decision(db, project.id, "产品定位已确认，进入 PRD 阶段",
                      reason="用户确认产品定位与差异点", source="阶段确认")
    db.commit()
    db.refresh(p)
    return _positioning_out(p)


# ── M3 PRD 与任务拆解 ──

@router.post("/projects/{project_id}/prd", response_model=TaskOut, status_code=202)
def start_prd(project_id: str, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    _require_confirmed(db, project.id, RequirementBrief, "需求摘要")
    pos = (
        db.query(Positioning)
        .filter(Positioning.project_id == project_id)
        .order_by(Positioning.version.desc())
        .first()
    )
    if pos is None or pos.status != "confirmed":
        raise LLMError("NOT_READY", "请先完成并确认产品定位（第 4 步）")
    if _active_task(db, project.id, "prd"):
        raise LLMError("CONFLICT", "已有进行中的 PRD 生成任务，请等待完成或刷新")
    _require_workflow_idle(db, project.id)
    task_worker.invalidate_downstream(db, project, "prd")
    task = Task(project_id=project.id, task_type="prd", status="queued")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_worker.enqueue(task.id)
    return task


@router.get("/projects/{project_id}/prd", response_model=PrdOut)
def get_prd(project_id: str, db: Session = Depends(get_db)):
    _require_project(db, project_id)
    doc = (
        db.query(ProductDoc)
        .filter(ProductDoc.project_id == project_id)
        .order_by(ProductDoc.version.desc())
        .first()
    )
    if doc is None:
        raise LLMError("NOT_FOUND", "尚未生成 PRD")
    return _prd_out(doc)


@router.put("/projects/{project_id}/prd", response_model=PrdOut)
def update_prd(project_id: str, payload: PrdUpdate, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    _require_workflow_idle(db, project.id)
    _require_confirmed(db, project.id, RequirementBrief, "需求摘要")
    _require_confirmed(db, project.id, Positioning, "产品定位")
    doc = (
        db.query(ProductDoc)
        .filter(ProductDoc.project_id == project_id)
        .order_by(ProductDoc.version.desc())
        .first()
    )
    if doc is None:
        raise LLMError("NOT_FOUND", "尚未生成 PRD")
    if doc.status == "stale" and payload.confirm:
        raise LLMError("NOT_READY", "上游内容已更新，请重新生成 PRD 后再确认")
    if payload.sections is not None:
        valid_ref_keys = {
            e.ref_key for e in db.query(CompetitorEvidence)
            .filter(CompetitorEvidence.project_id == project_id).all()
        }
        sections, _unverified = prd.audit_sections(payload.sections, valid_ref_keys)
        if sections != json.loads(doc.sections or "[]"):
            _invalidate_from(db, project, "prd")
        doc.sections = json.dumps(sections, ensure_ascii=False)
    if payload.confirm:
        doc.status = "confirmed"
        _advance_stage(project, "tasks")
        _log_decision(db, project.id, "PRD 已确认，进入任务拆解阶段",
                      reason="用户确认 PRD（MVP 范围并入版本规划章节）", source="阶段确认")
    db.commit()
    db.refresh(doc)
    return _prd_out(doc)


@router.post("/projects/{project_id}/tasks", response_model=TaskOut, status_code=202)
def start_tasks(project_id: str, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    doc = (
        db.query(ProductDoc)
        .filter(ProductDoc.project_id == project_id)
        .order_by(ProductDoc.version.desc())
        .first()
    )
    if doc is None:
        raise LLMError("NOT_READY", "请先生成 PRD")
    if doc.status != "confirmed":
        raise LLMError("NOT_READY", "请先确认 PRD（第 5 步）")
    if _active_task(db, project.id, "tasks"):
        raise LLMError("CONFLICT", "已有进行中的任务拆解，请等待完成或刷新")
    _require_workflow_idle(db, project.id)
    _require_confirmed(db, project.id, RequirementBrief, "需求摘要")
    _require_confirmed(db, project.id, Positioning, "产品定位")
    task_worker.invalidate_downstream(db, project, "tasks")
    task = Task(project_id=project.id, task_type="tasks", status="queued")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_worker.enqueue(task.id)
    return task


@router.get("/projects/{project_id}/tasks", response_model=list[DevTaskOut])
def get_tasks(project_id: str, db: Session = Depends(get_db)):
    _require_project(db, project_id)
    return [
        _task_out(t)
        for t in db.query(DevTask)
        .filter(DevTask.project_id == project_id)
        .order_by(DevTask.priority, DevTask.id)
        .all()
    ]


@router.patch("/projects/{project_id}/tasks/{task_id}", response_model=DevTaskOut)
def update_task(project_id: str, task_id: str, payload: DevTaskUpdate,
                db: Session = Depends(get_db)):
    """编辑单个研发任务（字段可选，None 表示不修改）。"""
    _require_project(db, project_id)
    t = db.query(DevTask).filter(DevTask.project_id == project_id, DevTask.id == task_id).first()
    if t is None:
        raise LLMError("NOT_FOUND", "任务不存在")
    data = payload.model_dump(exclude_unset=True)
    if data.get("priority") is not None and data["priority"] not in ("P0", "P1", "P2"):
        raise LLMError("INVALID_INPUT", "priority 不合法：P0/P1/P2")
    if data.get("module") is not None and data["module"] not in TASK_MODULES:
        raise LLMError("INVALID_INPUT", "module 不合法：" + "/".join(TASK_MODULES))
    for k, v in data.items():
        if v is not None:
            setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return _task_out(t)


@router.delete("/projects/{project_id}/tasks/{task_id}")
def delete_task(project_id: str, task_id: str, db: Session = Depends(get_db)):
    """删除单个研发任务。"""
    _require_project(db, project_id)
    t = db.query(DevTask).filter(DevTask.project_id == project_id, DevTask.id == task_id).first()
    if t is None:
        raise LLMError("NOT_FOUND", "任务不存在")
    db.delete(t)
    db.commit()
    return {"deleted": task_id}


@router.put("/projects/{project_id}/tasks")
def confirm_tasks(project_id: str, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    _require_workflow_idle(db, project.id)
    _require_confirmed(db, project.id, RequirementBrief, "需求摘要")
    _require_confirmed(db, project.id, Positioning, "产品定位")
    doc = _require_confirmed(db, project.id, ProductDoc, "PRD")
    tasks = db.query(DevTask).filter(DevTask.project_id == project_id).all()
    if any(t.created_at < doc.updated_at for t in tasks):
        raise LLMError("NOT_READY", "PRD 已更新，请重新生成研发任务并检查后再确认")
    if not any(t.priority == "P0" for t in tasks):
        raise LLMError("INVALID_INPUT", "请先确保存在 P0 任务再确认")
    if len(tasks) < 5:
        raise LLMError("INVALID_INPUT", "任务数量过少（≥5），请重新生成或补充任务")
    project.current_stage = "package"  # 任务确认后进入资料包导出（M4）
    _log_decision(db, project.id, "研发任务已确认，进入资料包导出阶段",
                  reason="用户确认研发任务（含 P0 与数量校验）", source="阶段确认")
    db.commit()
    return {"current_stage": project.current_stage}


# ── M4 迭代记录（Feedback / DecisionLog，s09 记忆系统）──

@router.post("/projects/{project_id}/feedback", response_model=FeedbackOut, status_code=201)
def add_feedback(project_id: str, payload: FeedbackCreate, db: Session = Depends(get_db)):
    """录入一条反馈（用户/老师/系统），支撑迭代记录页。"""
    _require_project(db, project_id)
    if payload.author_type not in ("user", "teacher", "system"):
        raise LLMError("INVALID_INPUT", "author_type 不合法：user/teacher/system")
    fb = Feedback(
        project_id=project_id,
        content=payload.content.strip(),
        affected_sections=(payload.affected_sections or "").strip(),
        author_type=payload.author_type,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


@router.get("/projects/{project_id}/feedback", response_model=list[FeedbackOut])
def list_feedback(project_id: str, db: Session = Depends(get_db)):
    """迭代记录页数据源：该项目全部反馈。"""
    _require_project(db, project_id)
    return (
        db.query(Feedback)
        .filter(Feedback.project_id == project_id)
        .order_by(Feedback.created_at, Feedback.id)
        .all()
    )


@router.get("/projects/{project_id}/decisions", response_model=list[DecisionLogOut])
def list_decisions(project_id: str, db: Session = Depends(get_db)):
    """决策台账数据源：该项目决策 + 系统级决策（project_id 为空）。"""
    _require_project(db, project_id)
    return (
        db.query(DecisionLog)
        .filter((DecisionLog.project_id == project_id) | (DecisionLog.project_id.is_(None)))
        .order_by(DecisionLog.created_at, DecisionLog.id)
        .all()
    )


# ── M4 资料包导出 ──

@router.post("/projects/{project_id}/export", response_model=ExportResult)
def export_project(project_id: str, payload: ExportCreate, db: Session = Depends(get_db)):
    """导出项目资料包（PRD 10.8）：聚合各阶段数据生成可独立阅读的文档，写 Export 表 + 埋点。"""
    project = _require_project(db, project_id)
    if payload.channel not in ("markdown", "feishu_copy", "github_issue"):
        raise LLMError("INVALID_INPUT", "channel 不合法：markdown/feishu_copy/github_issue")
    title, content = export_service.build_export(db, project, payload.channel)
    exp = Export(project_id=project_id, channel=payload.channel, status="success")
    db.add(exp)
    db.commit()
    db.refresh(exp)
    record_event("exported", project_id, export_id=exp.id, channel=payload.channel)
    return {"export_id": exp.id, "channel": payload.channel, "title": title, "content": content}


def _prd_out(doc: ProductDoc) -> dict:
    def _loads(text, default):
        try:
            return json.loads(text or "") if text else default
        except ValueError:
            return default

    return {
        "id": doc.id,
        "project_id": doc.project_id,
        "version": doc.version,
        "status": doc.status,
        "sections": _loads(doc.sections, []),
        "evidence_refs": _loads(doc.evidence_refs, []),
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


def _task_out(t: DevTask) -> dict:
    def _loads(text, default):
        try:
            return json.loads(text or "") if text else default
        except ValueError:
            return default

    return {
        "id": t.id,
        "module": t.module,
        "title": t.title,
        "description": t.description,
        "priority": t.priority,
        "acceptance_criteria": t.acceptance_criteria,
        "dependencies": _loads(t.dependencies, []),
        "source_refs": _loads(t.source_refs, []),
        "export_status": t.export_status,
    }


def _positioning_out(p: Positioning) -> dict:
    def _loads(text: str, default):
        try:
            return json.loads(text or "") if text else default
        except ValueError:
            return default

    return {
        "id": p.id,
        "project_id": p.project_id,
        "one_liner": p.one_liner,
        "target_users": p.target_users,
        "value_proposition": p.value_proposition,
        "differentiators": _loads(p.differentiators, []),
        "non_goals": p.non_goals,
        "comparison": _loads(p.comparison, []),
        "evidence_refs": _loads(p.evidence_refs, []),
        "version": p.version,
        "status": p.status,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def _require_workflow_idle(db: Session, project_id: str) -> None:
    if db.query(Task.id).filter(
        Task.project_id == project_id, Task.status.in_(["queued", "processing"]),
    ).first() is not None:
        raise LLMError("CONFLICT", "项目有排队或运行中的任务，请等待完成后再修改或确认")


def _require_confirmed(db: Session, project_id: str, model, label: str):
    latest = db.query(model).filter(model.project_id == project_id).order_by(model.version.desc()).first()
    if latest is None or latest.status != "confirmed":
        raise LLMError("NOT_READY", f"请先生成并确认最新{label}；上游更新后需重新生成")
    return latest


def _invalidate_from(db: Session, project: Project, stage: str) -> None:
    task_worker.invalidate_downstream(db, project, stage)
    model = {"clarify": RequirementBrief, "position": Positioning, "prd": ProductDoc}.get(stage)
    if model is not None:
        latest = db.query(model).filter(model.project_id == project.id).order_by(model.version.desc()).first()
        if latest is not None and latest.status != "stale":
            latest.status = "draft"


def _advance_stage(project: Project, stage: str) -> None:
    stages = ("clarify", "competitor", "position", "prd", "tasks", "package")
    if project.current_stage not in stages or stages.index(project.current_stage) < stages.index(stage):
        project.current_stage = stage


def _require_unreferenced_evidence(db: Session, project_id: str, keys: set[str]) -> None:
    if not keys:
        return

    def check_refs(refs):
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            raise LLMError("CONFLICT", "下游证据引用格式异常，无法安全删除")
        if keys.intersection(refs):
            raise LLMError("CONFLICT", "证据已被下游内容引用；可先调用 POST "
                           f"/api/v1/projects/{project_id}/competitors/{{competitor_id}}/detach-references "
                           "解除引用（保留正文），再重试删除")

    # Check every saved version, including nested positioning and PRD references.
    for model, fields in (
        (Positioning, ("evidence_refs", "differentiators")),
        (ProductDoc, ("evidence_refs", "sections")),
        (DevTask, ("source_refs",)),
        (DecisionLog, ("evidence_refs",)),
    ):
        for row in db.query(model).filter(model.project_id == project_id).all():
            for field in fields:
                try:
                    data = json.loads(getattr(row, field) or "[]")
                except ValueError as exc:
                    raise LLMError("CONFLICT", "下游证据引用格式异常，无法安全删除") from exc
                if field in ("differentiators", "sections"):
                    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                        raise LLMError("CONFLICT", "下游证据引用格式异常，无法安全删除")
                    for item in data:
                        check_refs(item.get("evidence_refs") or [])
                else:
                    check_refs(data)


def _without_refs(refs, keys: set[str]) -> list[str]:
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        raise LLMError("CONFLICT", "引用数据格式异常，未解除任何引用，请先修复数据")
    return [ref for ref in refs if ref not in keys]


def _require_competitor(db: Session, project_id: str, competitor_id: str) -> Competitor:
    _require_project(db, project_id)
    comp = db.get(Competitor, competitor_id)
    if comp is None or comp.project_id != project_id:
        raise LLMError("NOT_FOUND", "竞品不存在")
    return comp


def _require_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != DEFAULT_USER_ID:
        raise LLMError("NOT_FOUND", "项目不存在")
    return project


def _log_decision(db: Session, project_id: str, decision: str,
                  reason: str = "", source: str = "阶段确认") -> None:
    """记录一条项目决策（s09 记忆系统运行期写入）。"""
    db.add(DecisionLog(
        project_id=project_id,
        decision=decision,
        reason=reason,
        source=source,
    ))


def _active_task(db: Session, project_id: str, task_type: str) -> Task | None:
    """是否已有 queued/processing 的同类型任务（幂等保护，避免重复花钱）。"""
    return (
        db.query(Task)
        .filter(Task.project_id == project_id, Task.task_type == task_type,
                Task.status.in_(["queued", "processing"]))
        .first()
    )


def _missing_key_items(db: Session, project_id: str) -> list[str]:
    """必答项（目标用户/场景/成功指标）中尚未回答的维度。"""
    qas = db.query(ClarificationQA).filter(ClarificationQA.project_id == project_id).all()
    answered = {qa.dimension for qa in qas if qa.answer.strip()}
    return [d for d in KEY_DIMENSIONS if d not in answered]


def _question_out(qa: ClarificationQA) -> dict:
    return {
        "id": qa.id,
        "round_num": qa.round_num,
        "dimension": qa.dimension,
        "question": qa.question,
        "hint": qa.hint,
        "answer": qa.answer,
        "skipped": qa.skipped,
        "required": qa.dimension in KEY_DIMENSIONS,
    }
