"use client";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ArrowRight, Check, Copy, Download, Loader2, Plus, RefreshCw, Save, Sparkles, Trash2, X } from "lucide-react";
import type { Brief, Competitor, Positioning, Prd, Project, TaskOut } from "../lib/types";
import { displayValue, exportChannels, exportWorkflow, validateEvidenceUrl, loadWorkflow, parseRecommendations, pollWorkflowTask, projectPath, workflowRequest, WorkflowError, type ExportChannel, type MarkdownExport, type Recommendation, type WorkflowData } from "../lib/workflow-api";
import { emptyEvidenceDraft, emptyWorkflowDrafts, parseWorkflowDrafts, type EvidenceDraft, type WorkflowDrafts } from "../lib/workflow-api";
import { deleteWorkflowCompetitor, evidenceFetchJob, isDefiniteSubmissionRejection, parseWorkflowJob, sameCompetitor, type WorkflowJob as Job } from "../lib/workflow-api";
import { workflowBlocker } from "../lib/workflow-api";

type Props = { project: Project; onChanged: () => Promise<void> };
const stages = [["clarify", "需求澄清"], ["competitor", "竞品"], ["position", "定位"], ["prd", "PRD"], ["tasks", "研发任务"], ["package", "资料包"]] as const;
const isStage = (value: string | null): value is (typeof stages)[number][0] => stages.some(([key]) => key === value);
function requiredStage(data: WorkflowData): (typeof stages)[number][0] {
  if (!data.questions.length || !data.brief || data.brief.status === "stale") return "clarify";
  if (data.brief.status !== "confirmed" || !data.competitors.length || !Object.values(data.evidences).some((items) => items.length)) return "competitor";
  if (data.positioning?.status !== "confirmed") return "position";
  if (data.prd?.status !== "confirmed") return "prd";
  if (data.tasks.length < 5 || !data.tasks.some((task) => task.priority === "P0") || data.currentStage !== "package") return "tasks";
  return "package";
}
const labels: Record<string, string> = {
  one_liner: "一句话概述", target_users: "目标用户", scenarios: "使用场景", pains: "痛点", goals: "目标",
  non_goals: "不做什么", success_metrics: "成功指标", external_systems: "外部系统", knowledge_sources: "知识来源",
  open_questions: "待确认问题", value_proposition: "价值主张", differentiators: "差异点", comparison: "竞品对比", evidence_refs: "证据引用",
};
const fieldLabels: Record<string, string> = { ...labels, point: "差异化要点", dimension: "对比维度", competitors: "竞品情况", our_product: "本产品", title: "标题", content: "内容", status: "状态", name: "名称", description: "描述", reason: "原因", question: "问题", answer: "回答", source: "来源", source_refs: "来源引用", dependencies: "依赖", priority: "优先级", acceptance_criteria: "验收标准" };
const statusLabel = (value: unknown) => ({ draft: "草稿", confirmed: "已确认", stale: "需更新", queued: "排队中", processing: "处理中", success: "已完成", failed: "失败" }[String(value)] ?? displayValue(value));
const intros: Record<string, string> = {
  clarify: "填写必答问题后生成需求摘要，回答会一并提交；选答可补充更多背景。",
  competitor: "添加带官网链接的竞品后自动抓取证据（会调用模型）；缺少链接时只需补充网址。手动补充证据为选填。",
  position: "确认需求摘要并添加竞品后生成定位，核对差异点、竞品对比和证据引用，再确认。",
  prd: "确认定位后生成 PRD，逐章检查产品范围、需求及验收要求，再确认。",
  tasks: "确认 PRD 后生成研发任务，检查验收标准和依赖；至少 5 个任务且包含 P0 才能确认。",
  package: "选择导出格式并生成资料包，再复制或下载。飞书和 GitHub 导出为可粘贴内容，不会自动发布。",
};

function Content({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (depth < 12) {
    if (typeof value === "string" && /^[\[{]/.test(value.trim())) {
      try { const parsed: unknown = JSON.parse(value); if (parsed && typeof parsed === "object") return <Content value={parsed} depth={depth + 1} />; } catch { /* Keep ordinary prose intact. */ }
    }
    if (Array.isArray(value)) return value.length ? <ul className="workflow-content">{value.map((item, index) => <li key={index}><Content value={item} depth={depth + 1} /></li>)}</ul> : <p>暂无内容</p>;
    if (value && typeof value === "object") return <dl className="workflow-document">{Object.entries(value).map(([key, item]) => <div key={key}><dt>{fieldLabels[key] ?? key}</dt><dd><Content value={key === "status" ? statusLabel(item) : item} depth={depth + 1} /></dd></div>)}</dl>;
  } else if (value && typeof value === "object") return <p>内容层级过深，请在资料包中查看。</p>;
  return <pre className="workflow-content" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontFamily: "inherit" }}>{displayValue(value) || "暂无内容"}</pre>;
}
function Document({ value }: { value: Record<string, unknown> }) {
  return <dl className="workflow-document">{Object.entries(labels).filter(([key]) => key in value).map(([key, label]) => <div key={key}><dt>{label}</dt><dd><Content value={value[key]} /></dd></div>)}</dl>;
}

// A keyed session prevents old project responses and local drafts crossing project boundaries.
export default function WorkflowPanel(props: Props) {
  return <WorkflowSession key={props.project.id} {...props} />;
}

function WorkflowSession({ project, onChanged }: Props) {
  const [stage, setStage] = useState(stages.some(([key]) => key === project.current_stage) ? project.current_stage : "clarify");
  const [focusAction, setFocusAction] = useState<string | null>(null);
  const [data, setData] = useState<WorkflowData | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState(false);
  const [questionGroup, setQuestionGroup] = useState<"required" | "optional">("required");
  const groupedQuestions = (data?.questions ?? []).filter((question) => Boolean(question.required) === (questionGroup === "required"));
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [exported, setExported] = useState<MarkdownExport | null>(null);
  const [channel, setChannel] = useState<ExportChannel>("markdown");
  const [drafts, setDrafts] = useState<WorkflowDrafts>(emptyWorkflowDrafts);
  const [storageWarning, setStorageWarning] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [competitorErrors, setCompetitorErrors] = useState<Record<string, string>>({});
  const deletedCompetitors = useRef(new Set<string>());
  const workflowTop = useRef<HTMLElement | null>(null);
  const draftsRef = useRef<WorkflowDrafts>(emptyWorkflowDrafts());
  const active = useRef<AbortController | null>(null);
  const mounted = useRef(false);
  const retry = useRef<(() => void) | null>(null);
  const base = projectPath(project.id);
  const storageKey = `workflow-task:${project.id}`;
  const draftKey = `workflow-drafts:${project.id}`;
  const current = (signal: AbortSignal) => mounted.current && !signal.aborted && active.current?.signal === signal;
  const actionId = (name: string) => `workflow-action-${project.id}-${name}`;
  const activeStageIndex = stages.findIndex(([key]) => key === stage);

  function navigate(nextStage: string, target = "stage") {
    if (isStage(nextStage)) {
      const url = new URL(window.location.href);
      if (url.searchParams.get("stage") !== nextStage) {
        url.searchParams.set("stage", nextStage);
        window.history.pushState(window.history.state, "", url);
      }
    }
    setStage(nextStage); setFocusAction(target);
    if (nextStage === "clarify") setQuestionGroup("required");
  }

  useEffect(() => {
    const syncStage = () => {
      const value = new URL(window.location.href).searchParams.get("stage");
      if (!data) return;
      if (isStage(value)) setStage(value);
    };
    const initial = new URL(window.location.href).searchParams.get("stage");
    if (data && isStage(initial)) syncStage();
    window.addEventListener("popstate", syncStage);
    return () => window.removeEventListener("popstate", syncStage);
    // The keyed workflow session reads the URL once and follows browser history.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  useEffect(() => {
    if (focusAction) workflowTop.current?.scrollIntoView({ block: "start" });
  }, [stage, focusAction]);

  useEffect(() => {
    if (!focusAction || busy) return;
    const target = document.getElementById(actionId(focusAction));
    const fallback = document.getElementById(`workflow-stage-${project.id}`);
    const focusable = target && !target.hasAttribute("disabled") ? target : fallback;
    focusable?.focus({ preventScroll: true });
    if (focusAction !== "stage") focusable?.scrollIntoView({ block: "nearest" });
    setFocusAction(null);
    // The project ID is fixed by the keyed session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, focusAction, busy, data]);

  function rememberJob(next: Job | null) {
    setJob(next);
    try { if (next) sessionStorage.setItem(storageKey, JSON.stringify(next)); else sessionStorage.removeItem(storageKey); } catch { /* Storage may be unavailable in private browsing. */ }
  }

  function saveDrafts(next: WorkflowDrafts) {
    draftsRef.current = next;
    setDrafts(next);
    try { sessionStorage.setItem(draftKey, JSON.stringify(next)); }
    catch { setStorageWarning("浏览器无法保存会话草稿；当前输入仍保留在页面内，离开项目或刷新前请先提交。"); }
  }

  function changeEvidence(id: string, field: keyof EvidenceDraft, value: string) {
    const currentDrafts = draftsRef.current;
    saveDrafts({ ...currentDrafts, evidences: { ...currentDrafts.evidences, [id]: { ...(currentDrafts.evidences[id] ?? emptyEvidenceDraft()), [field]: value } } });
  }

  function changeAnswer(id: string, value: string) {
    const next = { ...answers, [id]: value };
    const changed = Object.fromEntries((data?.questions ?? []).filter((q) => next[q.id] !== q.answer).map((q) => [q.id, next[q.id] ?? ""]));
    setAnswers(next); setDirty(Object.keys(changed).length > 0);
    saveDrafts({ ...draftsRef.current, answers: changed });
  }

  async function refresh(signal: AbortSignal, resetAnswers = false) {
    const result = await loadWorkflow(project.id, signal);
    if (!current(signal)) return;
    const requestedStage = new URL(window.location.href).searchParams.get("stage");
    const required = requiredStage(result);
    const nextStage = isStage(requestedStage) ? requestedStage : required;
    setStage(nextStage);
    const url = new URL(window.location.href);
    if (url.searchParams.get("stage") !== nextStage) {
      url.searchParams.set("stage", nextStage);
      window.history.replaceState(window.history.state, "", url);
    }
    result.competitors = result.competitors.filter((c) => !deletedCompetitors.current.has(c.id));
    for (const id of deletedCompetitors.current) delete result.evidences[id];
    setData(result);
    const saved = resetAnswers ? {} : draftsRef.current.answers;
    const merged = Object.fromEntries(result.questions.map((q) => [q.id, Object.hasOwn(saved, q.id) ? saved[q.id] : q.answer]));
    const changed = Object.fromEntries(result.questions.filter((q) => merged[q.id] !== q.answer).map((q) => [q.id, merged[q.id]]));
    setAnswers(merged); setDirty(Object.keys(changed).length > 0);
    saveDrafts({ ...draftsRef.current, answers: changed });
  }

  async function run(label: string, action: (signal: AbortSignal) => Promise<void>, again?: () => void) {
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setBusy(label); setError(""); setNotice(""); retry.current = again ?? null;
    try { await action(controller.signal); }
    catch (reason) { if (current(controller.signal)) setError(reason instanceof Error ? reason.message : displayValue(reason)); }
    finally { if (current(controller.signal)) { active.current = null; setBusy(""); } }
  }

  function reload() {
    void run("读取阶段数据", async (signal) => { await refresh(signal); }, reload);
  }

  useEffect(() => {
    mounted.current = true;
    try {
      const restored = parseWorkflowDrafts(sessionStorage.getItem(draftKey));
      draftsRef.current = restored; setDrafts(restored);
    } catch { setStorageWarning("浏览器无法读取会话草稿，请在离开项目之前提交输入。"); }
    try {
      const saved = parseWorkflowJob(sessionStorage.getItem(storageKey));
      if (saved) setJob(saved);
    } catch { /* Invalid saved state must not prevent loading the project. */ }
    reload();
    return () => { mounted.current = false; active.current?.abort(); active.current = null; };
    // The parent keys this session by project ID; callbacks use the latest rendered props.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function generate(path: string, label: string, resume?: Job) {
    void run(label, (signal) => processJob(resume ?? { path, label }, signal), reload);
  }

  async function processJob(initial: Job, signal: AbortSignal) {
    let pending = initial;
    const { path, label } = pending;
    // A retry may query an existing task, but must never resubmit a paid operation.
    retry.current = () => { if (pending.id) generate(path, label, pending); else reload(); };
      if (!pending.id) {
        if (path === "/brief" && dirty) {
          setBusy("提交回答");
          await workflowRequest(base + "/clarify/answers", signal, "POST", { answers: data?.questions.map((q) => ({ question_id: q.id, answer: answers[q.id] ?? "" })) });
          if (!current(signal)) return;
          await refresh(signal, true);
          if (!current(signal)) return;
          setBusy(label);
        }
        rememberJob(pending);
        let task: TaskOut;
        try {
          task = await workflowRequest<TaskOut>(base + path, signal, "POST", pending.payload);
        } catch (reason) {
          if (current(signal) && isDefiniteSubmissionRejection(reason)) rememberJob(null);
          throw reason;
        }
        if (!current(signal)) return;
        if (!task || typeof task.id !== "string" || !task.id || task.project_id !== project.id) throw new Error("未收到有效任务 ID，提交结果不明。请先刷新核对，勿直接重复生成。");
        pending = { ...pending, id: task.id }; rememberJob(pending);
      }
      let task: TaskOut;
      try {
        task = await pollWorkflowTask(pending.id!, project.id, signal, (status) => {
          if (current(signal)) setBusy(`${label} · ${status.status === "queued" ? "排队中" : "处理中"}`);
        });
      } catch (reason) {
        if (current(signal) && reason instanceof WorkflowError && (reason.code === "TASK_FAILED" || reason.status === 404)) {
          pending = { ...pending, id: undefined }; rememberJob(null);
        }
        throw reason;
      }
      if (!current(signal)) return;
      rememberJob(null);
      // Retrying a refresh after success must never submit another paid generation.
      retry.current = reload;
      if (path === "/competitors/recommend") {
        const items = parseRecommendations(task); setRecommendations(items);
        if (!items.length) setNotice("未返回推荐竞品，可以手动添加。");
      }
      await refresh(signal, path === "/clarify/questions");
      if (!current(signal)) return;
      setExported(null);
      if (path === "/brief") navigate("competitor", "brief-confirm");
      await onChanged();
      if (current(signal)) setNotice(`${label}完成`);
  }

  function fetchWebsite(competitor: Competitor, url: string) {
    try {
      const next = evidenceFetchJob(competitor.id, url);
      generate(next.path, next.label, next);
    } catch (reason) { setError(reason instanceof Error ? reason.message : displayValue(reason)); }
  }

  function createCompetitor(payload: { name: string; url: string; positioning?: string }, after: () => void) {
    if (!payload.name.trim()) { setError("请输入竞品名称"); return; }
    if (payload.url.trim()) {
      try { payload = { ...payload, url: validateEvidenceUrl(payload.url) }; }
      catch (reason) { setError(reason instanceof Error ? reason.message : displayValue(reason)); return; }
    }
    void run("添加竞品", async (signal) => {
      // A lost create response is reconciled with GET; retries must not create a second competitor.
      rememberJob({ path: "/competitors", label: "添加竞品" });
      let competitor: Competitor;
      try {
        competitor = await workflowRequest<Competitor>(`${base}/competitors`, signal, "POST", payload);
      } catch (reason) {
        if (current(signal) && isDefiniteSubmissionRejection(reason)) rememberJob(null);
        throw reason;
      }
      if (!current(signal)) return;
      if (!competitor || typeof competitor.id !== "string" || !competitor.id) throw new Error("添加结果不明，请刷新核对竞品列表，不要重复添加。");
      rememberJob(null); after(); setExported(null);
      setRecommendations((items) => items.filter((item) => !sameCompetitor(item, competitor)));
      setData((previous) => previous ? { ...previous, competitors: [...previous.competitors.filter((c) => c.id !== competitor.id), competitor], evidences: { ...previous.evidences, [competitor.id]: [] } } : previous);
      if (payload.url.trim()) {
        await processJob(evidenceFetchJob(competitor.id, payload.url), signal);
      } else {
        await refresh(signal);
        if (!current(signal)) return;
        await onChanged();
        if (current(signal)) setNotice("竞品已添加，补充官网链接即可抓取证据。");
      }
    }, reload);
  }

  function mutate(path: string, method: string, body: unknown, label: string, after?: () => void, nextStage?: string) {
    void run(label, async (signal) => {
      const result = await workflowRequest<Brief | Positioning | Prd | { current_stage: string }>(base + path, signal, method, body);
      if (!current(signal)) return;
      after?.(); setExported(null); retry.current = reload;
      if (nextStage) {
        // Apply the committed response before slower refreshes or parent callbacks.
        setData((previous) => previous ? {
          ...previous, currentStage: nextStage,
          ...(path === "/brief" ? { brief: result as Brief } : path === "/positioning" ? { positioning: result as Positioning } : path === "/prd" ? { prd: result as Prd } : {}),
        } : previous);
        navigate(nextStage);
        setNotice(`${label}已完成`);
      }
      await refresh(signal, path === "/clarify/answers");
      if (!current(signal)) return;
      await onChanged();
      if (current(signal)) setNotice(`${label}完成`);
    }, reload);
  }

  const locked = !!busy || !!job || !data;
  const lockReason = busy ? `请等待${busy}完成，或停止等待。` : job ? (job.id ? "请先继续查询未结束的任务。" : "上次生成的提交结果不明，请先刷新核对。") : !data ? "阶段数据尚未加载，请刷新或重试。" : "";
  const action = (label: string, click: () => void, reason = "", icon: ReactNode = <Sparkles size={16} />, key?: string) => <span><button id={key ? actionId(key) : undefined} type="button" className="primary-button" disabled={locked || !!reason} title={lockReason || reason || undefined} onClick={click}>{icon}{label}</button>{reason && !lockReason && <small className="workflow-hint">{reason}</small>}</span>;
  const confirm = (path: string, reason: string, nextStage: string) => {
    const artifact = path === "/brief" ? data?.brief : path === "/positioning" ? data?.positioning : path === "/prd" ? data?.prd : null;
    if (artifact?.status === "stale") {
      const label = path === "/brief" ? "需求摘要" : path === "/positioning" ? "定位" : "PRD";
      const prerequisite = path === "/brief" ? briefReason : path === "/positioning" ? positioningReason : prdReason;
      return action(`重新生成${label}`, () => generate(path, `生成${label}`), prerequisite, <RefreshCw size={16} />, path === "/brief" ? "brief-update" : `${path.slice(1)}-generate`);
    }
    const confirmed = path === "/brief" ? data?.brief?.status === "confirmed" : path === "/positioning" ? data?.positioning?.status === "confirmed" : path === "/prd" ? data?.prd?.status === "confirmed" : data?.currentStage === "package";
    const key = `${path.slice(1)}-confirm`;
    if (confirmed) return <button id={actionId(key)} type="button" className="primary-button" onClick={() => navigate(nextStage)}><ArrowRight size={16} />进入{stages.find(([id]) => id === nextStage)?.[1]}</button>;
    const label = path === "/brief" ? stage === "competitor" ? "确认摘要并继续竞品" : "确认摘要并进入竞品" : `确认并进入${stages.find(([id]) => id === nextStage)?.[1]}`;
    return action(label, () => mutate(path, "PUT", path === "/tasks" ? undefined : { confirm: true }, "确认", undefined, nextStage), reason, <Check size={16} />, key);
  };
  const requiredMissing = data?.questions.some((q) => q.required && !(answers[q.id] ?? "").trim()) ?? true;
  const briefReason = !data?.questions.length ? "请先生成澄清问题。" : requiredMissing ? "请补齐必答项。" : "";
  const competitorReason = (data?.competitors.length ?? 0) >= 3 ? "已达到 3 个竞品上限。" : "";
  const positioningReason = data?.brief?.status !== "confirmed" ? "请先在需求澄清阶段确认摘要。" : !data?.competitors.length ? "请先添加至少 1 个竞品。" : !Object.values(data.evidences).some((items) => items.length) ? "请先抓取官网或手动添加至少一张竞品证据卡。" : "";
  const prdReason = data?.positioning?.status !== "confirmed" ? "请先确认产品定位。" : "";
  const tasksReason = data?.prd?.status !== "confirmed" ? "请先确认 PRD。" : "";
  const taskConfirmReason = !data?.tasks.length ? "请先生成研发任务。" : data.tasks.length < 5 ? "至少需要 5 个任务，请重新生成。" : !data.tasks.some((t) => t.priority === "P0") ? "必须包含 P0 任务，请重新生成。" : "";
  const prerequisite = ({ clarify: data?.brief ? "" : briefReason, tasks: taskConfirmReason } as Record<string, string>)[stage];
  const blocker = data ? workflowBlocker(stage, data) : null;
  const confirmationReason = (document: { status: string } | null | undefined) => !document ? "请先生成本阶段产物。" : "";

  function addCompetitor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget; const values = new FormData(form);
    const name = String(values.get("name") || "").trim();
    if (!name) { setError("请输入竞品名称"); return; }
    createCompetitor({ name, url: String(values.get("url") || "").trim() }, () => saveDrafts({ ...draftsRef.current, competitor: { name: "", url: "" } }));
  }

  function addEvidence(event: FormEvent<HTMLFormElement>, competitorId: string) {
    event.preventDefault();
    const form = event.currentTarget; const values = new FormData(form);
    let source_url: string;
    try { source_url = validateEvidenceUrl(String(values.get("source_url") || "")); }
    catch (reason) { setError(reason instanceof Error ? reason.message : displayValue(reason)); return; }
    const structured_claim = String(values.get("structured_claim") || "").trim();
    if (!structured_claim) { setError("请输入证据结论"); return; }
    mutate(`/competitors/${encodeURIComponent(competitorId)}/evidences`, "POST", {
      source_url, structured_claim, evidence_type: values.get("evidence_type"), source_type: "用户输入", confidence: "用户补充",
      raw_excerpt: String(values.get("raw_excerpt") || ""),
    }, "保存证据", () => {
      const evidences = { ...draftsRef.current.evidences };
      delete evidences[competitorId];
      saveDrafts({ ...draftsRef.current, evidences });
    });
  }

  function deleteCompetitor(competitor: Competitor) {
    void run("删除竞品", async (signal) => {
      setCompetitorErrors((previous) => ({ ...previous, [competitor.id]: "" }));
      try {
        await deleteWorkflowCompetitor(project.id, competitor.id, signal);
      } catch (reason) {
        if (current(signal)) setCompetitorErrors((previous) => ({ ...previous, [competitor.id]: reason instanceof Error ? reason.message : displayValue(reason) }));
        return;
      }
      if (!current(signal)) return;
      deletedCompetitors.current.add(competitor.id);
      setRecommendations((items) => items.filter((item) => !sameCompetitor(item, competitor)));
      const evidences = { ...draftsRef.current.evidences };
      delete evidences[competitor.id];
      saveDrafts({ ...draftsRef.current, evidences });
      setData((previous) => {
        if (!previous) return previous;
        const remainingEvidence = { ...previous.evidences };
        delete remainingEvidence[competitor.id];
        return { ...previous, competitors: previous.competitors.filter((item) => item.id !== competitor.id), evidences: remainingEvidence };
      });
      setDeletingId(null); setExported(null); retry.current = reload;
      await onChanged();
      if (current(signal)) setNotice(`已删除竞品「${competitor.name}」`);
    }, reload);
  }

  function exportPackage() {
    setExported(null);
    void run("导出资料包", async (signal) => {
      const result = await exportWorkflow(project.id, channel, signal);
      if (current(signal)) { setExported(result); setNotice("资料包已生成"); }
    }, exportPackage);
  }

  return <section ref={workflowTop} className="workflow-panel" aria-label="项目工作流">
    <div className="workflow-toolbar">
      <h2>项目流程</h2>
      <button type="button" className="icon-button" title={busy ? lockReason : "刷新阶段数据"} aria-label="刷新阶段数据" disabled={!!busy} onClick={reload}><RefreshCw size={17} /></button>
    </div>
    <div className="workflow-tabs" role="tablist" aria-label="阶段">{stages.map(([key, title], index) => <button type="button" key={key} id={`workflow-tab-${project.id}-${key}`} role="tab" aria-selected={stage === key} aria-controls={`workflow-stage-${project.id}`} tabIndex={stage === key ? 0 : -1} disabled={index > activeStageIndex} title={index > activeStageIndex ? "请完成当前步骤后再继续" : undefined} className={`workflow-tab${stage === key ? " workflow-tab-active" : ""}`} onClick={() => navigate(key)} onKeyDown={(event) => {
      const offset = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
      if (!offset && event.key !== "Home" && event.key !== "End") return;
      event.preventDefault(); const next = event.key === "Home" ? 0 : event.key === "End" ? activeStageIndex : (index + offset + stages.length) % stages.length;
      if (next > activeStageIndex) { setNotice("请完成当前步骤后再继续。"); return; }
      navigate(stages[next][0]); document.getElementById(`workflow-tab-${project.id}-${stages[next][0]}`)?.focus();
    }}>{index + 1}. {title}</button>)}</div>
    {busy && <div className="workflow-status" role="status"><Loader2 size={16} />{busy}<button type="button" className="secondary-button" onClick={() => {
      active.current?.abort(); active.current = null; setBusy(""); setNotice("已停止等待；已提交的后台任务不会取消。刷新数据或继续查询可查看结果。");
    }}><X size={16} />停止等待</button></div>}
    {error && <div className="workflow-error" role="alert"><Content value={error} />{!busy && retry.current && <button type="button" className="secondary-button" onClick={() => retry.current?.()}><RefreshCw size={16} />{job?.id ? "重试查询" : "刷新核对"}</button>}</div>}
    {notice && <p className="workflow-status" role="status">{notice}</p>}
    {storageWarning && <p className="workflow-error" role="status">{storageWarning}</p>}
    {job && !busy && <div className="workflow-status">{job.id ? <><span>{job.label}：等待结果</span><button type="button" className="secondary-button" onClick={() => generate(job.path, job.label, job)}><RefreshCw size={16} />继续查询原任务</button></> : <>
      <p>{job.label}：提交结果不明，后台可能已生成并计费。刷新仅核对已有产物；后端不支持按项目找回丢失的任务 ID，推荐结果也可能无法恢复。</p>
      <button type="button" className="secondary-button" onClick={reload}><RefreshCw size={16} />刷新核对（不重新生成）</button>
      <button type="button" className="secondary-button" onClick={() => { rememberJob(null); setNotice("已保留当前产物；如仍需生成，请主动点击对应阶段的生成按钮。"); }}><Check size={16} />已核对，保留现有结果</button>
      {job.path !== "/competitors" && <button type="button" className="secondary-button" onClick={() => generate(job.path, job.label, { ...job, id: undefined })}><Sparkles size={16} />已核对，重新生成（可能重复计费）</button>}
    </>}</div>}
    <div className="workflow-stage" id={`workflow-stage-${project.id}`} role="tabpanel" tabIndex={-1} aria-labelledby={`workflow-tab-${project.id}-${stage}`} aria-busy={!!busy}>
      <header className="workflow-intro"><h3>{stage === "competitor" ? `竞品 ${data?.competitors.length ?? 0}/3` : stages.find(([key]) => key === stage)?.[1]}</h3><p>{intros[stage]}</p>{lockReason && <p className="workflow-hint">{lockReason}</p>}{prerequisite && <p className="workflow-hint">{prerequisite}</p>}{blocker && <div className="workflow-blocker"><p>{blocker.reason}</p><button type="button" className="secondary-button" onClick={() => navigate(blocker.stage, blocker.action)}><ArrowRight size={16} />{blocker.label}</button></div>}</header>
      {stage === "competitor" && data?.brief?.status === "draft" && <section className="workflow-brief-review" aria-label="需求摘要确认"><h3>需求摘要待确认 · v{data.brief.version}</h3><p className="workflow-hint">摘要已生成。核对后可在此确认并继续竞品阶段，无需返回上一步。</p><div className="workflow-actions">{confirm("/brief", "", "competitor")}</div><details className="brief-disclosure" open><summary>查看需求摘要全文</summary><Document value={data.brief} /></details></section>}
      {stage === "clarify" && <>
        {data?.brief && <section className="workflow-brief-review" aria-label="需求摘要确认"><h3>需求摘要 · {statusLabel(data.brief.status)} · v{data.brief.version}</h3><div className="workflow-actions">{dirty ? action("更新摘要并保存回答", () => generate("/brief", "生成需求摘要"), briefReason, <Sparkles size={16} />, data.brief.status === "stale" ? "brief-update" : "brief-confirm") : confirm("/brief", "", "competitor")}</div>{dirty && <p className="workflow-hint">回答有未提交修改，请先更新摘要再确认。</p>}<details className="brief-disclosure" key={data.brief.id + "-" + data.brief.version + "-" + data.brief.status} open={data.brief.status !== "confirmed"}><summary>查看需求摘要全文</summary><Document value={data.brief} /></details></section>}
        <div className="workflow-actions">{action(data?.questions.length ? "重新生成问题" : "生成问题", () => generate("/clarify/questions", "生成问题"), dirty ? "回答有修改，请先通过下一步提交。" : "", <Sparkles size={16} />, "questions")}</div>
        <div className="workflow-form clarify-form">
          {!!data?.questions.length && <div className="question-groups" role="group" aria-label="问题分组">{(["required", "optional"] as const).map((group) => {
            const questions = data.questions.filter((q) => Boolean(q.required) === (group === "required"));
            return <button type="button" key={group} aria-pressed={questionGroup === group} onClick={() => { setQuestionGroup(group); }}>{group === "required" ? "必答" : "选答"} <span>{questions.filter((q) => (answers[q.id] ?? "").trim()).length}/{questions.length}</span></button>;
          })}</div>}
          {!!data?.questions.length && !groupedQuestions.length && <p className="workflow-hint">本轮没有{questionGroup === "required" ? "必答" : "选答"}问题。</p>}
          {groupedQuestions.map((q) => <label className="form-label question-editor" key={q.id}>{displayValue(q.question)}{q.hint && <span className="workflow-hint">{displayValue(q.hint)}</span>}<textarea id={groupedQuestions[0]?.id === q.id ? actionId("answers") : undefined} className="field" rows={3} disabled={locked} value={answers[q.id] ?? ""} onChange={(event) => changeAnswer(q.id, event.target.value)} /></label>)}
        </div>
        <div className="workflow-actions">{!data?.brief ? action("下一步：生成需求摘要", () => generate("/brief", "生成需求摘要"), briefReason, <Sparkles size={16} />, "brief-generate") : <button id={actionId("brief-generate")} type="button" className="secondary-button" disabled={locked || !!briefReason} title={lockReason || briefReason || undefined} onClick={() => generate("/brief", "生成需求摘要")}><RefreshCw size={16} />重新生成摘要</button>}</div>
      </>}
      {stage === "competitor" && <>
        {!competitorReason && <><div className="workflow-actions">{action("推荐竞品", () => generate("/competitors/recommend", "推荐竞品"))}</div>
        <form className="workflow-form" onSubmit={addCompetitor}><label className="form-label">竞品名称<input className="field" id={actionId("competitor-add")} name="name" value={drafts.competitor.name} onChange={(event) => saveDrafts({ ...draftsRef.current, competitor: { ...draftsRef.current.competitor, name: event.target.value } })} required maxLength={200} disabled={locked} /></label><label className="form-label">官网链接（选填）<input className="field" name="url" type="url" value={drafts.competitor.url} onChange={(event) => saveDrafts({ ...draftsRef.current, competitor: { ...draftsRef.current.competitor, url: event.target.value } })} disabled={locked} /></label><button className="secondary-button" disabled={locked || !!competitorReason} title={lockReason || competitorReason || undefined}><Plus size={16} />{drafts.competitor.url.trim() ? "添加并抓取官网" : "添加竞品"}</button></form>
        {recommendations.filter((item) => !data?.competitors.some((c) => sameCompetitor(item, c))).map((item, index) => <article className="workflow-item" key={`${item.name}-${index}`}><div className="workflow-competitor-heading"><h3>{item.name}</h3><button type="button" className="icon-button" title="移除推荐（未保存）" aria-label={"移除推荐 " + item.name} onClick={() => setRecommendations((items) => items.filter((candidate) => candidate !== item))}><X size={16} /></button></div><p className="workflow-hint">推荐信息 · 模型推荐，未经搜索核实</p><Content value={item.positioning} /><Content value={item.url} /><div className="workflow-actions">{action(item.url ? "添加并抓取官网" : "添加竞品", () => createCompetitor(item, () => setRecommendations((items) => items.filter((candidate) => candidate !== item))), (data?.competitors.some((c) => c.name === item.name) ? "该竞品已添加。" : ""), <Plus size={16} />)}</div></article>)}
        </>}
        {data?.competitors.map((c) => <article className="workflow-item" key={c.id}><div className="workflow-competitor-heading"><h3>{displayValue(c.name)}</h3>{deletingId !== c.id && <button type="button" className="icon-button" title={lockReason || "删除竞品"} aria-label={"删除竞品 " + c.name} disabled={locked} onClick={() => setDeletingId(c.id)}><Trash2 size={16} /></button>}</div>
          <div className="workflow-competitor-actions">{deletingId === c.id ? <div className="workflow-delete-confirm" role="group" aria-label={"确认删除竞品 " + c.name}><p>删除「{c.name}」及其证据？若证据已被下游引用，将解除引用并把下游标为需更新；正文保留。进行中的项目任务会阻止删除。</p><div className="workflow-delete-controls"><button type="button" className="danger-button" style={{ minWidth: 112 }} aria-busy={busy === "删除竞品"} disabled={locked} title={lockReason || undefined} onClick={() => deleteCompetitor(c)}>{busy === "删除竞品" ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}{busy === "删除竞品" ? "删除中…" : "确认删除"}</button><button type="button" className="secondary-button" disabled={!!busy} title={busy ? lockReason : undefined} onClick={() => setDeletingId(null)}>取消</button></div></div> : null}{competitorErrors[c.id] && <div className="workflow-error" role="alert"><Content value={competitorErrors[c.id]} /><button type="button" className="secondary-button" disabled={!!busy} title={busy ? lockReason : undefined} onClick={reload}><RefreshCw size={16} />刷新核对</button></div>}</div>
<Content value={c.url} />{c.positioning && <section className="workflow-recommendation"><h4>推荐或录入信息</h4><Content value={c.positioning} /><p className="workflow-hint">不等同于已核实的证据。</p></section>}
          <div className="workflow-fetch">{c.url ? action((data.evidences[c.id] ?? []).some((evidence) => evidence.source_type !== "用户输入") ? "重新抓取官网（新增证据）" : "抓取官网证据", () => fetchWebsite(c, c.url)) : <form className="workflow-form" onSubmit={(event) => { event.preventDefault(); fetchWebsite(c, draftsRef.current.evidences[c.id]?.source_url ?? ""); }}><label className="form-label">官网链接<input className="field" type="url" required name="fetch_url" placeholder="https://example.com" value={drafts.evidences[c.id]?.source_url ?? ""} onChange={(event) => changeEvidence(c.id, "source_url", event.target.value)} disabled={locked} /></label><button className="secondary-button" disabled={locked} title={lockReason || undefined}><Sparkles size={16} />抓取官网证据</button></form>}<p className="workflow-hint">抓取会调用模型并新增一张证据卡；自动提炼不代表已经核实。</p></div>
          {c.url && <details className="workflow-fetch-override"><summary>更换抓取链接</summary><form className="workflow-form" onSubmit={(event) => { event.preventDefault(); fetchWebsite(c, draftsRef.current.evidences[c.id]?.source_url ?? ""); }}><label className="form-label">替代抓取链接<input className="field" type="url" name="fetch_override_url" required placeholder="https://example.com/product" disabled={locked} value={drafts.evidences[c.id]?.source_url ?? ""} onChange={(event) => changeEvidence(c.id, "source_url", event.target.value)} /></label><button type="submit" className="secondary-button" disabled={locked} title={lockReason || undefined}><Sparkles size={16} />使用此链接抓取</button></form></details>}
          {(data.evidences[c.id] ?? []).map((e) => <section className="workflow-evidence" key={e.id}><h4>{e.source_type === "用户输入" ? "手动补充证据" : "抓取证据"} · {displayValue(e.ref_key)}</h4><dl className="workflow-document"><dt>证据类型</dt><dd>{displayValue(e.evidence_type)}</dd><dt>结论</dt><dd><Content value={e.structured_claim} /></dd><dt>来源类型</dt><dd>{displayValue(e.source_type)}</dd><dt>实际证据来源</dt><dd><Content value={e.source_url} /></dd><dt>原文摘录</dt><dd><Content value={e.raw_excerpt} /></dd><dt>对本产品的启发</dt><dd><Content value={e.implication} /></dd><dt>置信度</dt><dd>{displayValue(e.confidence) || "待核查"}</dd><dt>抓取时间</dt><dd>{displayValue(e.fetched_at) || "未记录"}</dd></dl></section>)}
          <details className="workflow-manual-evidence"><summary>手动补充证据（选填）</summary><form className="workflow-form" onSubmit={(event) => addEvidence(event, c.id)}><label className="form-label">证据来源链接<input className="field" name="source_url" type="url" value={drafts.evidences[c.id]?.source_url ?? ""} onChange={(event) => changeEvidence(c.id, "source_url", event.target.value)} required placeholder="https://example.com" title="请输入包含主机名的 http/https 链接" onInput={(event) => event.currentTarget.setCustomValidity("")} onBlur={(event) => { try { validateEvidenceUrl(event.currentTarget.value); event.currentTarget.setCustomValidity(""); } catch (reason) { event.currentTarget.setCustomValidity(reason instanceof Error ? reason.message : "链接格式不正确"); } }} disabled={locked} /></label><label className="form-label">证据结论<textarea className="field" name="structured_claim" value={drafts.evidences[c.id]?.structured_claim ?? ""} onChange={(event) => changeEvidence(c.id, "structured_claim", event.target.value)} required rows={3} disabled={locked} /></label><label className="form-label">证据类型<select className="field" name="evidence_type" value={drafts.evidences[c.id]?.evidence_type ?? "定位"} onChange={(event) => changeEvidence(c.id, "evidence_type", event.target.value)} disabled={locked}>{["定位", "功能", "流程", "集成", "输出物", "定价", "用户", "限制"].map((type) => <option key={type}>{type}</option>)}</select></label><label className="form-label">原文摘录（选填）<textarea className="field" name="raw_excerpt" value={drafts.evidences[c.id]?.raw_excerpt ?? ""} onChange={(event) => changeEvidence(c.id, "raw_excerpt", event.target.value)} rows={3} disabled={locked} /></label><button className="secondary-button" disabled={locked} title={lockReason || undefined}><Save size={16} />保存证据</button></form></details>
        </article>)}
        <div className="workflow-actions">{data && <button type="button" className="primary-button" onClick={() => { const required = workflowBlocker("position", data); if (data.brief?.status === "draft") navigate("competitor", "brief-confirm"); else navigate(required?.stage ?? "position", required?.action ?? "positioning-generate"); }}><ArrowRight size={16} />{data.brief?.status === "draft" ? "先确认需求摘要" : workflowBlocker("position", data)?.label ?? "下一步：产品定位"}</button>}</div>
      </>}
      {stage === "position" && <><div className="workflow-actions">{data?.positioning?.status !== "stale" && action("生成定位", () => generate("/positioning", "生成定位"), positioningReason, <Sparkles size={16} />, "positioning-generate")}{confirm("/positioning", confirmationReason(data?.positioning), "prd")}</div>{data?.positioning ? <><p>定位 · {statusLabel(data.positioning.status)} · v{data.positioning.version}</p><Document value={data.positioning} /></> : <p>尚未生成定位</p>}</>}
      {stage === "prd" && <><div className="workflow-actions">{data?.prd?.status !== "stale" && action("生成 PRD", () => generate("/prd", "生成 PRD"), prdReason, <Sparkles size={16} />, "prd-generate")}{confirm("/prd", confirmationReason(data?.prd), "tasks")}</div>{data?.prd ? <><p>PRD · {statusLabel(data.prd.status)} · v{data.prd.version}</p>{data.prd.sections.map((s, index) => <section className="workflow-document" key={index}><h3>{displayValue(s.title) || `章节 ${index + 1}`}</h3>{s.status && <p>{statusLabel(s.status)}</p>}<Content value={s.content} />{!!s.evidence_refs?.length && <Content value={s.evidence_refs} />}</section>)}</> : <p>尚未生成 PRD</p>}</>}
      {stage === "tasks" && <><div className="workflow-actions">{action("生成研发任务", () => generate("/tasks", "生成研发任务"), tasksReason, <Sparkles size={16} />, "tasks-generate")}{confirm("/tasks", taskConfirmReason, "package")}</div>{!data?.tasks.length && <p>尚未生成研发任务</p>}{data?.tasks.map((t) => <article className="workflow-item" key={t.id}><h3>{displayValue(t.priority)} · {displayValue(t.module)} · {displayValue(t.title)}</h3><Content value={t.description} /><h4>验收标准</h4><Content value={t.acceptance_criteria} /><h4>依赖任务</h4><Content value={t.dependencies} /><h4>来源引用</h4><Content value={t.source_refs} /></article>)}</>}
      {stage === "package" && <><label className="form-label">导出格式<select className="field" value={channel} disabled={!!busy} title={busy ? lockReason : undefined} onChange={(event) => { setChannel(event.target.value as ExportChannel); setExported(null); setError(""); setNotice(""); retry.current = null; }}>{exportChannels.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><div className="workflow-actions">{action("导出资料包", exportPackage, "", <Download size={16} />)}{exported && <>
        <button type="button" className="secondary-button" disabled={!!busy} title={busy ? lockReason : undefined} onClick={() => void run("复制资料包", async (signal) => { if (!navigator.clipboard) throw new Error("当前浏览器不支持剪贴板，请下载 Markdown"); await navigator.clipboard.writeText(exported.content); if (current(signal)) setNotice("已复制资料包"); })}><Copy size={16} />复制</button>
        <button type="button" className="secondary-button" onClick={() => { const url = URL.createObjectURL(new Blob([exported.content], { type: "text/markdown;charset=utf-8" })); const link = document.createElement("a"); link.href = url; link.download = `${(exported.title || project.name).replace(/[\\/:*?"<>|]/g, "_")}.md`; document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }}><Download size={16} />下载</button>
      </>}</div>{exported ? <><p>导出格式：{exportChannels.find((option) => option.value === exported.channel)?.label}</p><h3>{displayValue(exported.title)}</h3>{exported.channel === "github_issue" && <button type="button" className="secondary-button" disabled={!!busy} title={busy ? lockReason : undefined} onClick={() => void run("复制 Issue 标题", async (signal) => { if (!navigator.clipboard) throw new Error("当前浏览器不支持剪贴板"); await navigator.clipboard.writeText(exported.title); if (current(signal)) setNotice("已复制 Issue 标题"); })}><Copy size={16} />复制 Issue 标题</button>}<pre className="workflow-content" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{exported.content}</pre></> : <p>尚未导出资料包</p>}</>}
    </div>
  </section>;
}
