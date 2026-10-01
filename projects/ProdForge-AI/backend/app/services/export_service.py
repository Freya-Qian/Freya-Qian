"""项目资料包导出（M4）：聚合各阶段数据生成可独立阅读的 Markdown，及三通道变体。

三通道（PRD 10.8）：Markdown（P0）/ 飞书复制友好（P0，人工粘贴不调 API）/ GitHub issue 草稿（P1，不调 API）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.models import (
    Competitor,
    CompetitorEvidence,
    DecisionLog,
    DevTask,
    Feedback,
    Positioning,
    ProductDoc,
    Project,
    RequirementBrief,
)

GOAL_TYPE_CN = {"course": "课程作业", "portfolio": "作品集", "real": "真实开发", "team_review": "团队评审"}


def _loads(text, default):
    try:
        return json.loads(text or "") if text else default
    except ValueError:
        return default


def _latest(db, model, project_id):
    return (
        db.query(model)
        .filter(model.project_id == project_id)
        .order_by(model.version.desc() if hasattr(model, "version") else model.created_at.desc())
        .first()
    )


def build_markdown(db, project: Project) -> str:
    """生成完整资料包 Markdown（可脱离产品独立阅读）。"""
    brief = _latest(db, RequirementBrief, project.id)
    positioning = _latest(db, Positioning, project.id)
    doc = _latest(db, ProductDoc, project.id)
    competitors = db.query(Competitor).filter(Competitor.project_id == project.id).all()
    evidences = db.query(CompetitorEvidence).filter(CompetitorEvidence.project_id == project.id).all()
    tasks = (
        db.query(DevTask)
        .filter(DevTask.project_id == project.id)
        .order_by(DevTask.priority, DevTask.id)
        .all()
    )
    feedbacks = db.query(Feedback).filter(Feedback.project_id == project.id).all()
    decisions = (
        db.query(DecisionLog)
        .filter((DecisionLog.project_id == project.id) | (DecisionLog.project_id.is_(None)))
        .all()
    )

    ev_by_comp: dict[str, list] = {}
    for e in evidences:
        ev_by_comp.setdefault(e.competitor_id, []).append(e)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []

    # 标题 + 项目简介
    lines.append(f"# {project.name} 项目资料包")
    lines.append("")
    if positioning and positioning.one_liner:
        lines.append(f"> 一句话定位：{positioning.one_liner}")
        lines.append("")
    lines.append("## 一、项目简介")
    lines.append("")
    lines.append(f"- **项目名称**：{project.name}")
    lines.append(f"- **原始想法**：{project.idea}")
    lines.append(f"- **目标类型**：{GOAL_TYPE_CN.get(project.goal_type, project.goal_type)}")
    lines.append(f"- **当前阶段**：{project.current_stage}")
    lines.append(f"- **导出时间**：{now}")
    lines.append("")

    # 需求澄清摘要
    lines.append("## 二、需求澄清摘要")
    lines.append("")
    if brief:
        labels = {
            "one_liner": "一句话定义", "target_users": "目标用户", "scenarios": "核心场景",
            "pains": "痛点", "goals": "产品目标", "non_goals": "非目标",
            "success_metrics": "成功指标", "external_systems": "外部系统/数据源",
            "knowledge_sources": "领域知识来源", "open_questions": "待确认问题",
        }
        for field, label in labels.items():
            val = (getattr(brief, field) or "").strip()
            if val:
                lines.append(f"**{label}**：{val}")
                lines.append("")
    else:
        lines.append("（尚未生成需求摘要）")
        lines.append("")

    # 竞品证据与分析
    lines.append("## 三、竞品证据与分析")
    lines.append("")
    if competitors:
        for c in competitors:
            lines.append(f"### 竞品：{c.name}" + (f"（{c.url}）" if c.url else ""))
            lines.append("")
            for label, val in (("定位", c.positioning), ("目标用户", c.target_users),
                               ("关键功能", c.key_features), ("优势", c.strengths), ("不足", c.gaps)):
                if val:
                    lines.append(f"- **{label}**：{val}")
            for e in ev_by_comp.get(c.id, []):
                lines.append("")
                lines.append(f"**证据卡 {e.ref_key}**（{e.evidence_type} · {e.confidence} · {e.source_type}）")
                lines.append(f"- 结论：{e.structured_claim}")
                if e.implication:
                    lines.append(f"- 对本产品启发：{e.implication}")
                if e.source_url:
                    lines.append(f"- 来源：{e.source_url}")
            lines.append("")
    else:
        lines.append("（尚未添加竞品）")
        lines.append("")

    # 产品定位与差异点
    lines.append("## 四、产品定位与差异点")
    lines.append("")
    if positioning:
        if positioning.one_liner:
            lines.append(f"**一句话定位**：{positioning.one_liner}")
            lines.append("")
        if positioning.target_users:
            lines.append(f"**目标用户**：{positioning.target_users}")
            lines.append("")
        if positioning.value_proposition:
            lines.append(f"**核心价值主张**：{positioning.value_proposition}")
            lines.append("")
        if positioning.non_goals:
            lines.append(f"**不做什么**：{positioning.non_goals}")
            lines.append("")
        diffs = _loads(positioning.differentiators, [])
        if diffs:
            lines.append("**差异点**：")
            for d in diffs:
                if isinstance(d, dict):
                    refs = "、".join(d.get("evidence_refs") or []) or "无证据"
                    lines.append(f"- {d.get('point', '')}（证据：{refs}）")
            lines.append("")
        comparison = _loads(positioning.comparison, [])
        if comparison:
            lines.append("**竞品对比**：")
            lines.append("")
            for row in comparison:
                if isinstance(row, dict):
                    lines.append(f"- **{row.get('dimension', '')}**")
                    comps = row.get("competitors") or {}
                    for cn, cv in comps.items():
                        lines.append(f"  - {cn}：{cv}")
                    lines.append(f"  - 本产品：{row.get('our_product', '')}")
            lines.append("")
    else:
        lines.append("（尚未生成产品定位）")
        lines.append("")

    # PRD
    lines.append("## 五、PRD（带证据引用）")
    lines.append("")
    if doc:
        sections = _loads(doc.sections, [])
        for s in sections:
            title = s.get("title", "")
            status = s.get("status", "")
            refs = s.get("evidence_refs") or []
            flag = " ⚠️待确认" if status == "待确认" else ""
            ref_txt = f"（证据：{'、'.join(refs)}）" if refs else ""
            lines.append(f"### {title}{flag}{ref_txt}")
            lines.append("")
            lines.append(s.get("content", "").strip())
            lines.append("")
    else:
        lines.append("（尚未生成 PRD）")
        lines.append("")

    # 研发任务拆解（含 MVP 范围，已并入 PRD 版本规划章节）
    lines.append("## 六、研发任务拆解")
    lines.append("")
    if tasks:
        lines.append(f"共 {len(tasks)} 个任务：")
        lines.append("")
        for t in tasks:
            deps = "、".join(_loads(t.dependencies, []))
            refs = "、".join(_loads(t.source_refs, []))
            lines.append(f"### [{t.priority}] {t.title}（{t.module}）")
            lines.append("")
            if t.description:
                lines.append(t.description)
                lines.append("")
            if t.acceptance_criteria:
                lines.append(f"- 验收标准：{t.acceptance_criteria}")
            if deps:
                lines.append(f"- 依赖：{deps}")
            if refs:
                lines.append(f"- 来源追溯：{refs}")
            lines.append("")
    else:
        lines.append("（尚未生成研发任务）")
        lines.append("")

    # 待确认问题
    lines.append("## 七、待确认问题")
    lines.append("")
    unverified = []
    if doc:
        for s in _loads(doc.sections, []):
            if s.get("status") == "待确认":
                unverified.append(s.get("title", ""))
    if brief and (brief.open_questions or "").strip() and brief.open_questions.strip() != "无":
        lines.append(f"- {brief.open_questions.strip()}")
    if unverified:
        lines.append(f"- 以下 PRD 章节缺少证据支撑：{'、'.join(unverified)}")
    if not lines[-1].startswith("- "):
        lines.append("（无待确认问题）")
    lines.append("")

    # 迭代记录
    lines.append("## 八、迭代记录")
    lines.append("")
    if feedbacks:
        for f in feedbacks:
            author = {"user": "用户", "teacher": "老师", "system": "系统"}.get(f.author_type, f.author_type)
            sec = f"（影响：{f.affected_sections}）" if f.affected_sections else ""
            lines.append(f"- [{author}] {f.content}{sec}")
        lines.append("")
    if decisions:
        lines.append("**关键决策**：")
        for d in decisions:
            src = f"（{d.source}）" if d.source else ""
            lines.append(f"- {d.decision}{src}")
            if d.reason:
                lines.append(f"  - 依据：{d.reason}")
        lines.append("")
    if not feedbacks and not decisions:
        lines.append("（暂无迭代记录）")
        lines.append("")

    # 证据来源与引用说明
    lines.append("## 九、证据来源与引用说明")
    lines.append("")
    if evidences:
        for e in evidences:
            lines.append(f"- **{e.ref_key}**：{e.source_url or '（无来源链接）'}（{e.source_type} · {e.confidence}）")
        lines.append("")
    else:
        lines.append("（本项目暂无竞品证据卡）")
        lines.append("")

    # 交接说明
    lines.append("## 十、交接说明")
    lines.append("")
    stage_hint = {
        "clarify": "尚在需求澄清阶段，建议继续完成澄清与摘要。",
        "competitor": "尚在竞品证据阶段，建议继续添加竞品与证据。",
        "prd": "尚在 PRD 阶段，建议继续生成并确认 PRD。",
        "tasks": "尚在任务拆解阶段，建议确认研发任务后导出。",
        "package": "已完成研发任务拆解，资料包已完整，可进入评审或开发。",
    }.get(project.current_stage, "")
    lines.append(f"- 项目当前阶段：{project.current_stage}。{stage_hint}")
    lines.append("- 本资料包由「AI 产品工厂」生成，可脱离产品独立阅读。")
    lines.append("- 数据持久化于本地 SQLite，如需迁移请使用设置页的导出/导入。")
    lines.append("")

    return "\n".join(lines)


def build_export(db, project: Project, channel: str) -> tuple[str, str]:
    """按通道生成导出内容，返回 (标题, 内容)。"""
    markdown = build_markdown(db, project)
    if channel == "github_issue":
        # issue 标题 = 项目名 + 一句话定位；正文为去掉一级标题的资料包
        brief = _latest(db, RequirementBrief, project.id)
        one_liner = (brief.one_liner or project.idea) if brief else project.idea
        title = f"[项目资料包] {project.name}：{one_liner[:60]}"
        body = markdown.split("\n", 2)[-1] if markdown.startswith("# ") else markdown
        return title, body
    # markdown / feishu_copy 均为完整 Markdown（飞书支持 Markdown 粘贴）
    return f"{project.name} 项目资料包", markdown
