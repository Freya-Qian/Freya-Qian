"""M2 API 路由：账户 / 项目 / 数字人 Profile / 信息源 + M1 实体（全部按 user_id 隔离）。"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.config import EXPORT_DIR, TEMPLATE_DIR, UPLOAD_DIR, VIDEO_DIR, settings
from app.core.auth import get_current_user, generate_code, issue_token, revoke_token
from app.core.db import get_db
from app.core.llm import LLMError
from app.models import (
    AuthToken,
    AvatarProfile,
    Project,
    Script,
    ScriptVersion,
    Source,
    SourceItem,
    Topic,
    User,
    VerificationCode,
    VideoProject,
)
from app.schemas import (
    AgentRunRequest,
    AuthCodeRequest,
    AuthVerifyRequest,
    AuthVerifyResponse,
    ProfileCreate,
    ProfileOut,
    ProfileUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    RevertRequest,
    ScriptOut,
    ScriptUpdate,
    ScriptVersionOut,
    SourceCreate,
    SourceItemOut,
    SourceOut,
    SourceUpdate,
    TopicOut,
    UserOut,
    VideoCreate,
    VideoOut,
)
from app.services import agent, engine, guard, sources as sources_svc, stylize, video as video_svc, video_worker

router = APIRouter(prefix="/api/v1")

_PHONE_RE = re.compile(r"^\d{6,20}$")


# ---------- 输出构造 ----------


def _user_out(u: User) -> UserOut:
    return UserOut(id=u.id, phone=u.phone)


def _project_out(p: Project) -> ProjectOut:
    return ProjectOut(id=p.id, name=p.name, default_avatar_profile_id=p.default_avatar_profile_id, status=p.status)


def _profile_out(p: AvatarProfile) -> ProfileOut:
    return ProfileOut(
        id=p.id, project_id=p.project_id, name=p.name, avatar_type=p.avatar_type,
        template_id=p.template_id or 1,
        voice_type=p.voice_type, style_tags=p.style_tags or [], language=p.language,
        catchphrases=p.catchphrases or [], banned_phrases=p.banned_phrases or [],
        topic_preferences=p.topic_preferences or [], platform_preferences=p.platform_preferences or [],
        video_ratio=p.video_ratio,
    )


def _profile_avatar_path(p: AvatarProfile) -> Path:
    if p.avatar_asset_id:
        uploaded = UPLOAD_DIR / p.avatar_asset_id
        if uploaded.exists():
            return uploaded
    template = TEMPLATE_DIR / f"tpl_{p.template_id or 1}.png"
    if template.exists():
        return template
    return Path(video_svc.ensure_placeholder())


def _source_out(s: Source) -> SourceOut:
    return SourceOut(id=s.id, project_id=s.project_id, source_type=s.source_type, name=s.name, url=s.url, status=s.status)


def _item_out(s: SourceItem) -> SourceItemOut:
    return SourceItemOut(
        id=s.id, source_type=s.source_type, source_name=s.source_name,
        original_url=s.original_url, title=s.title, published_at=s.published_at,
        summary=s.summary, keywords=s.keywords or [], is_official=bool(s.is_official),
        cross_check_count=s.cross_check_count, credibility_score=s.credibility_score,
        video_potential_score=s.video_potential_score, status=s.status,
    )


def _topic_out(t: Topic) -> TopicOut:
    return TopicOut(
        id=t.id, source_item_id=t.source_item_id, title=t.title, angle=t.angle,
        one_liner=t.one_liner, summary=t.summary, key_facts=t.key_facts or [],
        source_urls=t.source_urls or [], score=t.score,
        score_breakdown=t.score_breakdown or {}, risk_level=t.risk_level,
        risk_flags=t.risk_flags or [], status=t.status,
    )


def _script_out(s: Script) -> ScriptOut:
    return ScriptOut(
        id=s.id, topic_id=s.topic_id, duration_target=s.duration_target,
        platform=s.platform, language=s.language, content=s.content,
        fact_claims=s.fact_claims or [], risk_flags=s.risk_flags or [],
        source_urls=s.source_urls or [], version=s.version, status=s.status,
    )


def _get_profile_for_topic(db: Session, topic: Topic, user_id: str) -> AvatarProfile | None:
    """沿 topic→source_item→source→project→profile 取 Profile，逐层校验归属（双重校验）。"""
    item = db.get(SourceItem, topic.source_item_id)
    if not item or not item.source_id or item.user_id != user_id:
        return None
    source = db.get(Source, item.source_id)
    if not source or source.user_id != user_id:
        return None
    project = db.get(Project, source.project_id)
    if not project or project.user_id != user_id or not project.default_avatar_profile_id:
        return None
    profile = db.get(AvatarProfile, project.default_avatar_profile_id)
    if not profile or profile.user_id != user_id:
        return None
    return profile


def _unlink_video_files(video_id: str) -> None:
    """删除本地生成物；失败不影响数据库清理，避免残留产物阻塞用户删除。"""
    for path in (
        VIDEO_DIR / f"{video_id}.mp4",
        VIDEO_DIR / f"{video_id}.srt",
        EXPORT_DIR / f"{video_id}.zip",
    ):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    for path in VIDEO_DIR.glob(f"{video_id}_cover.*"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _delete_video_tree(db: Session, v: VideoProject) -> None:
    _unlink_video_files(v.id)
    db.delete(v)


def _delete_script_tree(db: Session, s: Script, user_id: str) -> None:
    for v in db.query(VideoProject).filter(VideoProject.script_id == s.id, VideoProject.user_id == user_id).all():
        _delete_video_tree(db, v)
    for version in db.query(ScriptVersion).filter(ScriptVersion.script_id == s.id).all():
        db.delete(version)
    db.delete(s)


def _delete_topic_tree(db: Session, t: Topic, user_id: str) -> None:
    for s in db.query(Script).filter(Script.topic_id == t.id, Script.user_id == user_id).all():
        _delete_script_tree(db, s, user_id)
    db.delete(t)


def _delete_item_tree(db: Session, item: SourceItem, user_id: str) -> None:
    for t in db.query(Topic).filter(Topic.source_item_id == item.id, Topic.user_id == user_id).all():
        _delete_topic_tree(db, t, user_id)
    db.delete(item)


def _delete_profile_asset_files(prof: AvatarProfile) -> None:
    if not prof.avatar_asset_id:
        return
    uploaded = UPLOAD_DIR / prof.avatar_asset_id
    stylized = None
    if uploaded.exists():
        try:
            stylized = UPLOAD_DIR / f"stylized_{hashlib.sha256(uploaded.read_bytes()).hexdigest()[:16]}.png"
        except OSError:
            stylized = None
    try:
        uploaded.unlink(missing_ok=True)
    except OSError:
        pass
    if stylized:
        try:
            stylized.unlink(missing_ok=True)
        except OSError:
            pass


# ---------- 账户 ----------


@router.post("/auth/code")
def request_code(body: AuthCodeRequest, db: Session = Depends(get_db)):
    phone = body.phone.strip()
    if not _PHONE_RE.fullmatch(phone):
        raise LLMError("INVALID_INPUT", "手机号格式不正确")
    code = generate_code()
    from datetime import datetime, timedelta
    db.merge(VerificationCode(
        phone=phone, code=code,
        expires_at=datetime.now() + timedelta(minutes=5),
    ))
    db.commit()
    resp = {"ok": True}
    if settings.dev_mode:
        resp["dev_code"] = code  # 本地测试：验证码直接返回（真实短信上线前）
    return resp


@router.post("/auth/verify", response_model=AuthVerifyResponse)
def verify_code(body: AuthVerifyRequest, db: Session = Depends(get_db)):
    phone = body.phone.strip()
    if not _PHONE_RE.fullmatch(phone):
        raise LLMError("INVALID_INPUT", "手机号格式不正确")
    from datetime import datetime
    row = db.get(VerificationCode, phone)
    if not row or row.expires_at < datetime.now():
        raise LLMError("INVALID_INPUT", "验证码已过期，请重新获取")
    if row.code != body.code.strip():
        raise LLMError("INVALID_INPUT", "验证码错误")
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        user = User(id=engine._gen_id("usr"), phone=phone)
        db.add(user)
        db.flush()
    db.delete(row)
    db.commit()
    token = issue_token(db, user.id)
    return AuthVerifyResponse(token=token, user=_user_out(user))


@router.post("/auth/logout")
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    if authorization and authorization.startswith("Bearer "):
        revoke_token(db, authorization[len("Bearer "):].strip())
    return {"ok": True}


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


# ---------- 项目 ----------


@router.post("/projects", response_model=ProjectOut)
def create_project(body: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = Project(id=engine._gen_id("prj"), user_id=user.id, name=body.name, status="active")
    db.add(p)
    db.commit()
    db.refresh(p)
    return _project_out(p)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_project_out(p) for p in db.query(Project).filter(Project.user_id == user.id).all()]


@router.patch("/projects/{pid}", response_model=ProjectOut)
def update_project(pid: str, body: ProjectUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.get(Project, pid)
    if not p or p.user_id != user.id:
        raise LLMError("NOT_FOUND", "项目不存在")
    p.name = body.name
    db.commit()
    db.refresh(p)
    return _project_out(p)


@router.delete("/projects/{pid}")
def delete_project(pid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.get(Project, pid)
    if not p or p.user_id != user.id:
        raise LLMError("NOT_FOUND", "项目不存在")
    for s in db.query(Source).filter(Source.project_id == p.id, Source.user_id == user.id).all():
        for item in db.query(SourceItem).filter(SourceItem.source_id == s.id, SourceItem.user_id == user.id).all():
            _delete_item_tree(db, item, user.id)
        db.delete(s)
    for prof in db.query(AvatarProfile).filter(AvatarProfile.project_id == p.id, AvatarProfile.user_id == user.id).all():
        _delete_profile_asset_files(prof)
        db.delete(prof)
    db.delete(p)
    db.commit()
    return {"ok": True}


# ---------- 数字人 Profile ----------


@router.post("/projects/{pid}/profiles", response_model=ProfileOut)
def create_profile(pid: str, body: ProfileCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.get(Project, pid)
    if not p or p.user_id != user.id:
        raise LLMError("NOT_FOUND", "项目不存在")
    prof = AvatarProfile(
        id=engine._gen_id("pro"), user_id=user.id, project_id=p.id, name=body.name,
        template_id=body.template_id,
        avatar_type=body.avatar_type, voice_type=body.voice_type, style_tags=body.style_tags,
        language=body.language, catchphrases=body.catchphrases, banned_phrases=body.banned_phrases,
        topic_preferences=body.topic_preferences, platform_preferences=body.platform_preferences,
        video_ratio=body.video_ratio,
    )
    db.add(prof)
    if not p.default_avatar_profile_id:
        p.default_avatar_profile_id = prof.id
    db.commit()
    db.refresh(prof)
    return _profile_out(prof)


@router.get("/projects/{pid}/profiles", response_model=list[ProfileOut])
def list_profiles(pid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_profile_out(x) for x in db.query(AvatarProfile).filter(
        AvatarProfile.project_id == pid, AvatarProfile.user_id == user.id
    ).all()]


@router.patch("/profiles/{pid}", response_model=ProfileOut)
def update_profile(pid: str, body: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    prof = db.get(AvatarProfile, pid)
    if not prof or prof.user_id != user.id:
        raise LLMError("NOT_FOUND", "数字人 Profile 不存在")
    for field in ("name", "avatar_type", "voice_type", "style_tags", "language",
                  "catchphrases", "banned_phrases", "topic_preferences",
                  "platform_preferences", "video_ratio", "template_id"):
        val = getattr(body, field)
        if val is not None:
            setattr(prof, field, val)
    db.commit()
    db.refresh(prof)
    return _profile_out(prof)


@router.delete("/profiles/{pid}")
def delete_profile(pid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    prof = db.get(AvatarProfile, pid)
    if not prof or prof.user_id != user.id:
        raise LLMError("NOT_FOUND", "数字人 Profile 不存在")
    db.delete(prof)
    db.commit()
    return {"ok": True}


# ---------- 模板形象 ----------


@router.get("/templates")
def list_templates():
    templates = []
    for f in sorted(TEMPLATE_DIR.glob("tpl_*.png")):
        tid = int(f.stem.replace("tpl_", ""))
        templates.append({"id": tid, "name": f"模板 {tid}", "image_url": f"/api/v1/templates/{tid}/image"})
    return templates


@router.get("/templates/{tid}/image")
def template_image(tid: int):
    path = TEMPLATE_DIR / f"tpl_{tid}.png"
    if not path.exists():
        raise LLMError("NOT_FOUND", "模板不存在")
    return FileResponse(str(path), media_type="image/png")


# ---------- 信息源（配置） ----------


@router.post("/sources", response_model=SourceOut)
def create_source(body: SourceCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.get(Project, body.project_id)
    if not project or project.user_id != user.id:
        raise LLMError("NOT_FOUND", "项目不存在")
    if body.source_type in ("url", "rss") and not body.url.strip():
        raise LLMError("INVALID_INPUT", "URL/RSS 信息源需要填写链接")
    if body.source_type == "manual" and not body.content.strip():
        raise LLMError("INVALID_INPUT", "手动信息源需要填写正文")
    s = Source(
        id=engine._gen_id("src"), user_id=user.id, project_id=project.id, source_type=body.source_type,
        name=body.name or body.url, url=body.url, content=body.content, status="active",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _source_out(s)


@router.get("/sources", response_model=list[SourceOut])
def list_sources(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_source_out(s) for s in db.query(Source).filter(Source.user_id == user.id).order_by(Source.created_at.desc()).all()]


@router.patch("/sources/{sid}", response_model=SourceOut)
def update_source(sid: str, body: SourceUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(Source, sid)
    if not s or s.user_id != user.id:
        raise LLMError("NOT_FOUND", "信息源不存在")
    if body.name is not None:
        s.name = body.name
    if body.status is not None:
        if body.status not in ("active", "disabled"):
            raise LLMError("INVALID_INPUT", "状态只能是 active/disabled")
        s.status = body.status
    db.commit()
    db.refresh(s)
    return _source_out(s)


@router.delete("/sources/{sid}")
def delete_source(sid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(Source, sid)
    if not s or s.user_id != user.id:
        raise LLMError("NOT_FOUND", "信息源不存在")
    for item in db.query(SourceItem).filter(SourceItem.source_id == s.id, SourceItem.user_id == user.id).all():
        _delete_item_tree(db, item, user.id)
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.post("/sources/{sid}/fetch", response_model=list[SourceItemOut])
async def fetch_source(sid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(Source, sid)
    if not s or s.user_id != user.id:
        raise LLMError("NOT_FOUND", "信息源不存在")
    items = await sources_svc.fetch_source_items(db, s, user.id)
    db.commit()
    for it in items:
        db.refresh(it)
    return [_item_out(it) for it in items]


# ---------- 抓取条目（SourceItem） ----------


@router.get("/items", response_model=list[SourceItemOut])
def list_items(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_item_out(s) for s in db.query(SourceItem).filter(SourceItem.user_id == user.id).order_by(SourceItem.fetched_at.desc()).all()]


@router.post("/items/{iid}/summarize", response_model=SourceItemOut)
async def summarize_item(iid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(SourceItem, iid)
    if not s or s.user_id != user.id:
        raise LLMError("NOT_FOUND", "条目不存在")
    await engine.summarize_source(engine._client(), s)
    db.commit()
    db.refresh(s)
    return _item_out(s)


@router.delete("/items/{iid}")
def delete_item(iid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(SourceItem, iid)
    if not s or s.user_id != user.id:
        raise LLMError("NOT_FOUND", "条目不存在")
    _delete_item_tree(db, s, user.id)
    db.commit()
    return {"ok": True}


@router.post("/items/{iid}/topics", response_model=list[TopicOut])
async def create_topics(iid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(SourceItem, iid)
    if not s or s.user_id != user.id:
        raise LLMError("NOT_FOUND", "条目不存在")
    if s.status != "summarized":
        raise LLMError("PARSE_ERROR", "请先完成摘要生成")
    items = await engine.generate_topics(engine._client(), s)
    topics = []
    for it in items:
        t = Topic(
            id=engine._gen_id("tpc"), user_id=user.id, source_item_id=s.id,
            title=it.title, angle=it.angle, one_liner=it.one_liner,
            summary=s.summary, key_facts=it.key_facts,
            source_urls=it.source_urls or [s.original_url],
            score=it.score, score_breakdown=it.score_breakdown,
            risk_level=it.risk_level, risk_flags=it.risk_flags, status="new",
        )
        db.add(t)
        topics.append(t)
    db.commit()
    for t in topics:
        db.refresh(t)
    return [_topic_out(t) for t in topics]


# ---------- 选题 / 脚本 ----------


@router.get("/topics", response_model=list[TopicOut])
def list_topics(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_topic_out(t) for t in db.query(Topic).filter(Topic.user_id == user.id).order_by(Topic.created_at.desc()).all()]


@router.get("/topics/{tid}", response_model=TopicOut)
def get_topic(tid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.get(Topic, tid)
    if not t or t.user_id != user.id:
        raise LLMError("NOT_FOUND", "选题不存在")
    return _topic_out(t)


@router.post("/topics/{tid}/select", response_model=TopicOut)
def select_topic(tid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.get(Topic, tid)
    if not t or t.user_id != user.id:
        raise LLMError("NOT_FOUND", "选题不存在")
    t.status = "selected"
    db.commit()
    db.refresh(t)
    return _topic_out(t)


@router.delete("/topics/{tid}")
def delete_topic(tid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.get(Topic, tid)
    if not t or t.user_id != user.id:
        raise LLMError("NOT_FOUND", "选题不存在")
    _delete_topic_tree(db, t, user.id)
    db.commit()
    return {"ok": True}


@router.post("/topics/{tid}/scripts")
async def create_script(tid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.get(Topic, tid)
    if not t or t.user_id != user.id:
        raise LLMError("NOT_FOUND", "选题不存在")
    s = db.get(SourceItem, t.source_item_id)
    profile = _get_profile_for_topic(db, t, user.id)

    async def events():
        async for ev in engine.generate_script_stream(engine._client(), t, s, profile):
            if ev["type"] == "chunk":
                yield f"data: {json.dumps({'delta': ev['delta']}, ensure_ascii=False)}\n\n"
            elif ev["type"] == "error":
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                return
            elif ev["type"] == "done":
                data = ev["script"]
                script = Script(
                    id=engine._gen_id("scr"), user_id=user.id, topic_id=t.id,
                    duration_target=settings.script_duration,
                    platform=(profile.platform_preferences[0] if profile and profile.platform_preferences else "douyin"),
                    language=(profile.language if profile and profile.language else "zh"),
                    content=data["content"], fact_claims=data["fact_claims"],
                    risk_flags=data["risk_flags"], source_urls=data["source_urls"],
                    version=1, status="draft",
                )
                db.add(script)
                db.flush()
                db.add(ScriptVersion(
                    id=engine._gen_id("sv"), script_id=script.id, version=1,
                    content=script.content, fact_claims=script.fact_claims,
                    risk_flags=script.risk_flags, source_urls=script.source_urls,
                ))
                t.status = "scripted"
                db.commit()
                db.refresh(script)
                yield f"data: {json.dumps({'script': _script_out(script).model_dump()}, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/scripts", response_model=list[ScriptOut])
def list_scripts(
    project_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Script).filter(Script.user_id == user.id)
    if project_id:
        query = (
            query.join(Topic, Script.topic_id == Topic.id)
            .join(SourceItem, Topic.source_item_id == SourceItem.id)
            .join(Source, SourceItem.source_id == Source.id)
            .filter(Source.project_id == project_id)
        )
    return [_script_out(s) for s in query.order_by(Script.created_at.desc()).all()]


@router.patch("/scripts/{sid}", response_model=ScriptOut)
def update_script(sid: str, body: ScriptUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(Script, sid)
    if not s or s.user_id != user.id:
        raise LLMError("NOT_FOUND", "脚本不存在")
    new_version = s.version + 1
    db.add(ScriptVersion(
        id=engine._gen_id("sv"), script_id=s.id, version=new_version,
        content=body.content, fact_claims=s.fact_claims,
        risk_flags=s.risk_flags, source_urls=s.source_urls,
    ))
    s.content = body.content
    s.version = new_version
    db.commit()
    db.refresh(s)
    return _script_out(s)


@router.get("/scripts/{sid}", response_model=ScriptOut)
def get_script(sid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(Script, sid)
    if not s or s.user_id != user.id:
        raise LLMError("NOT_FOUND", "脚本不存在")
    return _script_out(s)


@router.delete("/scripts/{sid}")
def delete_script(sid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(Script, sid)
    if not s or s.user_id != user.id:
        raise LLMError("NOT_FOUND", "脚本不存在")
    _delete_script_tree(db, s, user.id)
    db.commit()
    return {"ok": True}


@router.get("/scripts/{sid}/versions", response_model=list[ScriptVersionOut])
def list_versions(sid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(Script, sid)
    if not s or s.user_id != user.id:
        raise LLMError("NOT_FOUND", "脚本不存在")
    rows = db.query(ScriptVersion).filter(ScriptVersion.script_id == sid).order_by(ScriptVersion.version.desc()).all()
    return [ScriptVersionOut(version=v.version, content=v.content, created_at=v.created_at.isoformat()) for v in rows]


@router.post("/scripts/{sid}/revert", response_model=ScriptOut)
def revert_script(sid: str, body: RevertRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(Script, sid)
    if not s or s.user_id != user.id:
        raise LLMError("NOT_FOUND", "脚本不存在")
    v = db.query(ScriptVersion).filter(ScriptVersion.script_id == sid, ScriptVersion.version == body.version).first()
    if not v:
        raise LLMError("NOT_FOUND", "该版本不存在")
    s.content = v.content
    s.fact_claims = v.fact_claims
    s.risk_flags = v.risk_flags
    s.source_urls = v.source_urls
    s.version = v.version
    db.commit()
    db.refresh(s)
    return _script_out(s)


@router.get("/scripts/{sid}/export")
def export_script(sid: str, user: User = Depends(get_current_user), format: str = Query(default="md"), db: Session = Depends(get_db)):
    s = db.get(Script, sid)
    if not s or s.user_id != user.id:
        raise LLMError("NOT_FOUND", "脚本不存在")
    if format == "txt":
        return {"content": s.content, "format": "txt"}
    sources = "\n".join(f"- {u}" for u in (s.source_urls or []))
    risks = "\n".join(f"- {r}" for r in (s.risk_flags or [])) or "- 无"
    claims = "\n".join(f"- {c}" for c in (s.fact_claims or [])) or "- 无"
    md = (
        f"# 口播脚本（{s.duration_target} 秒 / {s.platform}）\n\n"
        f"{s.content}\n\n"
        f"## 事实依据\n{claims}\n\n"
        f"## 风险提示\n{risks}\n\n"
        f"## 来源\n{sources}\n"
    )
    return {"content": md, "format": "md"}


# ---------- 照片上传 ----------

_ALLOWED_IMG = {".jpg", ".jpeg", ".png", ".webp"}
_MAX_PHOTO = 5 * 1024 * 1024


def _check_image(content: bytes, ext: str) -> bool:
    if ext in (".jpg", ".jpeg"):
        return content[:3] == b"\xff\xd8\xff"
    if ext == ".png":
        return content[:8] == b"\x89PNG\r\n\x1a\n"
    if ext == ".webp":
        return content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


@router.post("/profiles/{pid}/photo", response_model=ProfileOut)
async def upload_photo(pid: str, consent: bool = Form(False), file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    prof = db.get(AvatarProfile, pid)
    if not prof or prof.user_id != user.id:
        raise LLMError("NOT_FOUND", "数字人 Profile 不存在")
    if not consent:
        raise LLMError("INVALID_INPUT", "需确认：上传的是本人形象并授权在本产品内使用（PRD 11.2）")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_IMG:
        raise LLMError("INVALID_INPUT", "只支持 jpg/png/webp 图片")
    content = await file.read()
    if len(content) > _MAX_PHOTO:
        raise LLMError("INVALID_INPUT", "图片不能超过 5MB")
    if not _check_image(content, ext):
        raise LLMError("INVALID_INPUT", "文件真实类型与扩展名不符")
    fname = f"{prof.id}_{uuid4().hex[:8]}{ext}"
    (UPLOAD_DIR / fname).write_bytes(content)
    prof.avatar_asset_id = fname
    prof.avatar_consent_status = "granted"
    prof.avatar_type = "uploaded_self"
    db.commit()
    db.refresh(prof)
    return _profile_out(prof)


@router.get("/profiles/{pid}/avatar-preview")
async def avatar_preview(pid: str, refresh: bool = Query(False), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    prof = db.get(AvatarProfile, pid)
    if not prof or prof.user_id != user.id:
        raise LLMError("NOT_FOUND", "数字人 Profile 不存在")
    source_path = _profile_avatar_path(prof)
    preview_path = source_path
    if prof.avatar_asset_id:
        preview_path = Path(await stylize.stylize_avatar(str(source_path), force=refresh))
    media_type = "image/png" if preview_path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(str(preview_path), media_type=media_type)


# ---------- 视频任务 ----------


def _video_out(v: VideoProject) -> VideoOut:
    return VideoOut(
        id=v.id, script_id=v.script_id, avatar_profile_id=v.avatar_profile_id,
        version=v.version, video_url=v.video_url, cover_url=v.cover_url,
        subtitle_url=v.subtitle_url, export_package_url=v.export_package_url,
        status=v.status, error_message=v.error_message,
    )


@router.post("/scripts/{sid}/videos", response_model=VideoOut)
def create_video(
    sid: str,
    body: VideoCreate | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    s = db.get(Script, sid)
    if not s or s.user_id != user.id:
        raise LLMError("NOT_FOUND", "脚本不存在")
    t = db.get(Topic, s.topic_id)
    profile = None
    source_project_id = None
    if t:
        item = db.get(SourceItem, t.source_item_id)
        source = db.get(Source, item.source_id) if item else None
        source_project_id = source.project_id if source else None
    if body and body.avatar_profile_id:
        profile = db.get(AvatarProfile, body.avatar_profile_id)
        if (
            not profile
            or profile.user_id != user.id
            or (source_project_id and profile.project_id != source_project_id)
        ):
            raise LLMError("INVALID_INPUT", "请选择当前项目下的数字人形象")
    else:
        profile = _get_profile_for_topic(db, t, user.id) if t else None
    if not profile:
        raise LLMError("INVALID_INPUT", "请先创建数字人 Profile（模板形象或本人照片均可）")
    v = VideoProject(
        id=engine._gen_id("vid"), user_id=user.id, script_id=s.id,
        avatar_profile_id=profile.id if profile else None, version=1, status="queued",
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    video_worker.enqueue(v.id)
    return _video_out(v)


@router.get("/videos/{vid}", response_model=VideoOut)
def get_video(vid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    v = db.get(VideoProject, vid)
    if not v or v.user_id != user.id:
        raise LLMError("NOT_FOUND", "视频任务不存在")
    return _video_out(v)


@router.get("/videos", response_model=list[VideoOut])
def list_videos(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_video_out(v) for v in db.query(VideoProject).filter(VideoProject.user_id == user.id).order_by(VideoProject.created_at.desc()).all()]


@router.post("/videos/{vid}/retry", response_model=VideoOut)
def retry_video(vid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    v = db.get(VideoProject, vid)
    if not v or v.user_id != user.id:
        raise LLMError("NOT_FOUND", "视频任务不存在")
    if v.status not in ("failed", "success"):
        raise LLMError("INVALID_INPUT", "当前状态不可重试")
    v.status = "queued"
    v.error_message = ""
    db.commit()
    db.refresh(v)
    video_worker.enqueue(v.id)
    return _video_out(v)


@router.delete("/videos/{vid}")
def delete_video(vid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    v = db.get(VideoProject, vid)
    if not v or v.user_id != user.id:
        raise LLMError("NOT_FOUND", "视频任务不存在")
    _delete_video_tree(db, v)
    db.commit()
    return {"ok": True}


def _video_file(vid: str, user: User, db: Session, kind: str, media_type: str):
    v = db.get(VideoProject, vid)
    if not v or v.user_id != user.id:
        raise LLMError("NOT_FOUND", "视频任务不存在")
    if kind == "file":
        path = VIDEO_DIR / f"{vid}.mp4"
    elif kind == "cover":
        path = next(VIDEO_DIR.glob(f"{vid}_cover.*"), None)
    elif kind == "subtitle":
        path = VIDEO_DIR / f"{vid}.srt"
    elif kind == "export":
        path = EXPORT_DIR / f"{vid}.zip"
    else:
        raise LLMError("NOT_FOUND", "文件不存在")
    if not path or not Path(path).exists():
        raise LLMError("NOT_FOUND", "文件尚未生成")
    return FileResponse(str(path), media_type=media_type, filename=Path(path).name)


@router.get("/videos/{vid}/file")
def video_file(vid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _video_file(vid, user, db, "file", "video/mp4")


@router.get("/videos/{vid}/cover")
def video_cover(vid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _video_file(vid, user, db, "cover", "image/jpeg")


@router.get("/videos/{vid}/subtitle")
def video_subtitle(vid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _video_file(vid, user, db, "subtitle", "text/plain")


@router.get("/videos/{vid}/export")
def video_export(vid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _video_file(vid, user, db, "export", "application/zip")


# ---------- Agent（Agent Loop 入口，s01） ----------


def _persist_agent_script(
    db: Session,
    user: User,
    goal: str,
    script_data: dict,
    profile: AvatarProfile | None,
    project_id: str | None = None,
) -> Script:
    """把首页自动生成的脚本保存成正式脚本，后续可进入视频生成链路。"""
    project = None
    if project_id:
        candidate = db.get(Project, project_id)
        if candidate and candidate.user_id == user.id:
            project = candidate
    if not project and profile:
        project = db.get(Project, profile.project_id)
    if not project or project.user_id != user.id:
        project = db.query(Project).filter(Project.user_id == user.id).first()
    if not project:
        project = Project(id=engine._gen_id("prj"), user_id=user.id, name="我的第一个项目", status="active")
        db.add(project)
        db.flush()

    source = Source(
        id=engine._gen_id("src"), user_id=user.id, project_id=project.id,
        source_type="manual", name="首页自动生成", url="", content=goal, status="active",
    )
    db.add(source)
    db.flush()
    item = SourceItem(
        id=engine._gen_id("itm"), user_id=user.id, source_id=source.id,
        source_type="manual", source_name=source.name, original_url="",
        title=goal[:120], content_text=goal, summary="首页自动生成脚本",
        keywords=[], credibility_score=70, video_potential_score=80, status="summarized",
    )
    db.add(item)
    db.flush()
    topic = Topic(
        id=engine._gen_id("top"), user_id=user.id, source_item_id=item.id,
        title=goal[:120], angle="首页创作目标", one_liner=goal,
        summary="由首页创作目标自动生成", key_facts=script_data.get("fact_claims", []),
        source_urls=script_data.get("source_urls", []), score=80,
        risk_level="low", risk_flags=script_data.get("risk_flags", []), status="scripted",
    )
    db.add(topic)
    db.flush()
    script = Script(
        id=engine._gen_id("scr"), user_id=user.id, topic_id=topic.id,
        duration_target=settings.script_duration,
        platform=(profile.platform_preferences[0] if profile and profile.platform_preferences else "douyin"),
        language=(profile.language if profile and profile.language else "zh"),
        content=script_data.get("content", ""),
        fact_claims=script_data.get("fact_claims", []),
        risk_flags=script_data.get("risk_flags", []),
        source_urls=script_data.get("source_urls", []),
        version=1, status="draft",
    )
    db.add(script)
    db.flush()
    db.add(ScriptVersion(
        id=engine._gen_id("sv"), script_id=script.id, version=1,
        content=script.content, fact_claims=script.fact_claims,
        risk_flags=script.risk_flags, source_urls=script.source_urls,
    ))
    db.commit()
    db.refresh(script)
    return script


@router.post("/agent/run")
async def run_agent_endpoint(body: AgentRunRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """一句话目标 → Agent 自主完成抓取/摘要/选题/核查/脚本/自检，SSE 流式返回进度。"""
    # 内容安全：目标先过 guard（防敏感/破坏性输入）
    ok, reason = guard.content_guard(body.goal)
    if not ok:
        raise LLMError("INVALID_INPUT", reason)

    profile = None
    if body.profile_id:
        p = db.get(AvatarProfile, body.profile_id)
        if p and p.user_id == user.id:
            profile = p

    async def events():
        async for ev in agent.run_agent(engine._client(), user, body.goal, profile):
            script_data = ev.get("script") if isinstance(ev.get("script"), dict) else None
            if ev.get("type") == "done" and script_data and script_data.get("content"):
                script = _persist_agent_script(db, user, body.goal, script_data, profile, body.project_id)
                ev["script"] = _script_out(script).model_dump()
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
