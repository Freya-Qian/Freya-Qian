"use client";

import { ArrowLeft, ArrowRight, ArrowUp, BookOpen, Boxes, Check, ChevronRight, CircleHelp, FileText, Grid2X2, LayoutList, Loader2, MessageCirclePlus, Plus, RefreshCw, Search, Settings, Trash2, X } from "lucide-react";
import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import { api, getPendingProjectCreate } from "@/lib/api";
import type { ModelSettings, Project, SamplesResponse } from "@/lib/types";
import WorkflowPanel from "./workflow-panel";

type View = "home" | "projects" | "settings" | "guide";
const stageNames: Record<string, string> = { clarify: "需求澄清", competitor: "竞品", position: "定位", prd: "PRD", tasks: "研发任务", package: "资料包" };
const stageKeys = Object.keys(stageNames);
const goalNames = { real: "真实开发", portfolio: "作品集", course: "课程作业", team_review: "团队评审" };
const guideSteps = [
  ["配置模型", "在「设置」中填写 API Key、模型名称和接口地址，保存配置。生成内容时会使用这组模型配置。", "模型已配置"],
  ["创建项目", "回到「开始新项目」，描述目标用户、使用场景和想解决的问题，选择项目目标后提交。也可以在「项目」页点击「新建项目」，填写名称、产品想法和项目目标后创建。", "一个可持续推进的项目"],
  ["澄清需求", "打开项目的「需求澄清」，生成问题后填写必答项，可切换到选答补充背景。点击下一步提交回答并生成需求摘要，系统会进入竞品阶段。", "已生成的需求摘要"],
  ["收集竞品证据", "先在页面顶部核对并确认需求摘要，再选择推荐结果或添加竞品，最多三个。有官网链接时，添加后会自动抓取并整理证据；已有竞品可点击抓取。核对来源与结论，必要时展开手动补充。推荐信息本身不等于已核验的网页证据。", "确认后的需求摘要与竞品证据"],
  ["确认产品定位", "进入「定位」，生成定位和差异点，结合证据检查目标用户、价值主张与产品范围，再确认定位。", "确认后的产品方案"],
  ["生成 PRD", "在「PRD」中生成文档，逐章检查需求、功能、版本范围与待确认项，确认内容后进入研发任务。", "可评审的产品需求文档"],
  ["确认研发任务", "生成任务拆解，检查优先级、模块、依赖和验收标准，再确认任务清单。", "可执行的开发任务"],
  ["导出资料包", "进入「资料包」，选择 Markdown、飞书复制内容或 GitHub Issue 草稿，生成后下载或复制。导出不会自动发布到外部平台。", "可交接的项目资料"],
];

function errorText(error: unknown) { return error instanceof Error ? error.message : "操作失败，请重试。"; }
function dateLabel(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? "尚未更新" : date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" }); }

function readLocation(): { view: View; projectId: string } {
  const params = new URL(window.location.href).searchParams;
  const value = params.get("view");
  const projectId = params.get("project") || "";
  const view = (["home", "projects", "settings", "guide"] as string[]).includes(value || "") ? value as View : projectId ? "projects" : "home";
  return { view, projectId: view === "projects" ? projectId : "" };
}

function writeLocation(view: View, projectId: string, replace = false) {
  const url = new URL(window.location.href);
  const previousProjectId = url.searchParams.get("project") || "";
  url.searchParams.set("view", view);
  if (view === "projects" && projectId) url.searchParams.set("project", projectId);
  else url.searchParams.delete("project");
  if (view !== "projects" || !projectId || (previousProjectId && previousProjectId !== projectId)) url.searchParams.delete("stage");
  if (url.href !== window.location.href) window.history[replace ? "replaceState" : "pushState"](window.history.state, "", url);
}

export default function Home() {
  const [view, setView] = useState<View>("home");
  const [projects, setProjects] = useState<Project[]>([]);
  const [samples, setSamples] = useState<SamplesResponse | null>(null);
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [health, setHealth] = useState<"checking" | "ok" | "down">("checking");
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<{ error: boolean; text: string } | null>(null);
  const [idea, setIdea] = useState("");
  const [goal, setGoal] = useState("real");
  const [creating, setCreating] = useState(false);
  const [createPending, setCreatePending] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [query, setQuery] = useState("");
  const [stage, setStage] = useState("all");
  const [mode, setMode] = useState<"gallery" | "list">("gallery");
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const listGeneration = useRef(0);
  const settingsGeneration = useRef(0);
  const createLock = useRef(false);
  const homeRef = useRef<HTMLElement | null>(null);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  const [locationReady, setLocationReady] = useState(false);
  const selectedProject = useMemo(() => projects.find((project) => project.id === selectedId), [projects, selectedId]);

  const refreshProjects = useCallback(async () => {
    const generation = ++listGeneration.current;
    const result = await api.projects();
    if (generation !== listGeneration.current) return;
    setProjects(result);
    setProjectsLoaded(true);
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    const settingsRequest = ++settingsGeneration.current;
    try {
      await Promise.all([
        refreshProjects(),
        api.samples().then(setSamples),
        api.modelSettings().then((result) => { if (settingsRequest === settingsGeneration.current) setSettings(result); }),
        api.health().then(() => setHealth("ok")).catch(() => setHealth("down")),
      ]);
    } catch (error) { setNotice({ error: true, text: errorText(error) }); }
    finally { setLoading(false); }
  }, [refreshProjects]);

  useEffect(() => {
    const sync = () => {
      const location = readLocation();
      writeLocation(location.view, location.projectId, true);
      setView(location.view); setSelectedId(location.projectId); setNotice(null);
      setCreateOpen(false); setDeleteTarget(null);
      setLocationReady(true);
    };
    sync();
    window.addEventListener("popstate", sync);
    try {
      const pending = getPendingProjectCreate();
      if (pending) {
        setCreatePending(true); setIdea(pending.payload.idea); setNewName(pending.payload.name); setGoal(pending.payload.goal_type);
        setNotice({ error: true, text: "上次创建结果待核对，请点击核对创建结果。" });
      }
    } catch (error) { setCreatePending(true); setNotice({ error: true, text: errorText(error) }); }
    void refresh();
    return () => window.removeEventListener("popstate", sync);
  }, [refresh]);

  useEffect(() => {
    if (!locationReady || !projectsLoaded || !selectedId || selectedProject) return;
    writeLocation("projects", "", true);
    setSelectedId(""); setView("projects");
    setNotice({ error: true, text: "该项目不存在或已删除，已返回项目列表。" });
  }, [locationReady, projectsLoaded, selectedId, selectedProject]);

  useEffect(() => {
    const home = homeRef.current;
    if (view !== "home" || !home) return;
    const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let x = 50;
    let y = 50;
    const reset = () => {
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      home.classList.remove("has-pointer");
      home.style.setProperty("--pointer-x", "50%");
      home.style.setProperty("--pointer-y", "50%");
    };
    const handleMotionChange = (event: MediaQueryListEvent) => { if (event.matches) reset(); };
    const move = (event: PointerEvent) => {
      if (event.pointerType === "touch" || motionPreference.matches) return;
      const bounds = home.getBoundingClientRect();
      x = Math.max(0, Math.min(100, ((event.clientX - bounds.left) / bounds.width) * 100));
      y = Math.max(0, Math.min(100, ((event.clientY - bounds.top) / bounds.height) * 100));
      if (frame) return;
      frame = requestAnimationFrame(() => {
        home.style.setProperty("--pointer-x", `${x}%`);
        home.style.setProperty("--pointer-y", `${y}%`);
        home.classList.add("has-pointer");
        frame = 0;
      });
    };
    home.addEventListener("pointermove", move, { passive: true });
    home.addEventListener("pointerleave", reset, { passive: true });
    motionPreference.addEventListener("change", handleMotionChange);
    return () => {
      home.removeEventListener("pointermove", move);
      home.removeEventListener("pointerleave", reset);
      motionPreference.removeEventListener("change", handleMotionChange);
      reset();
    };
  }, [view]);

  function navigate(next: View, projectId = "", replace = false) {
    writeLocation(next, projectId, replace);
    setView(next); setSelectedId(projectId); setNotice(null);
  }
  function openProject(project: Project) { navigate("projects", project.id); }
  function askDelete(project: Project) { setDeleteTarget(project); setDeleteError(""); }

  async function create(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if ((!idea.trim() && !createPending) || createLock.current) return;
    createLock.current = true;
    setCreating(true);
    try {
      const title = (createOpen || createPending ? newName.trim() : "") || idea.trim().split(/[，。！？,!?\n]/)[0].slice(0, 36);
      const project = await api.createProject({ name: title || "新产品项目", idea: idea.trim(), goal_type: goal });
      ++listGeneration.current;
      setProjects((current) => [project, ...current.filter((item) => item.id !== project.id)]);
      setCreateOpen(false);
      setNewName("");
      setIdea("");
      openProject(project);
      setNotice({ error: false, text: "项目已创建，从生成澄清问题开始。" });
    } catch (error) { setNotice({ error: true, text: errorText(error) }); }
    finally {
      try { setCreatePending(!!getPendingProjectCreate()); } catch { setCreatePending(true); }
      createLock.current = false; setCreating(false);
    }
  }

  async function removeProject() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await api.deleteProject(deleteTarget.id);
      try {
        sessionStorage.removeItem(`workflow-drafts:${deleteTarget.id}`);
        sessionStorage.removeItem(`workflow-task:${deleteTarget.id}`);
      } catch { /* Deletion remains successful when browser storage is unavailable. */ }
      ++listGeneration.current;
      setProjects((current) => current.filter((item) => item.id !== deleteTarget.id));
      if (readLocation().projectId === deleteTarget.id) navigate("projects", "", true);
      setDeleteTarget(null);
      setNotice({ error: false, text: "项目及关联资料已删除。" });
    } catch (error) { setDeleteError(errorText(error)); }
    finally { setDeleting(false); }
  }

  const filtered = projects.filter((project) => (stage === "all" || stage === project.current_stage) && (project.name + project.idea).toLowerCase().includes(query.trim().toLowerCase()));
  const title = view === "home" ? "工作空间" : view === "settings" ? "模型设置" : view === "guide" ? "使用指南" : selectedProject ? "项目工作台" : "全部项目";

  return <main className="app-frame">
    <aside className="nav-rail">
      <button className="brand-lockup" onClick={() => navigate("home")} aria-label="ProdForge AI 首页"><span className="brand-logo"><Image src="/prodforge-logo.svg" alt="" width={112} height={112} priority /></span><span>ProdForge AI</span></button>
      <nav className="nav-items" aria-label="主导航">
        {([{ key: "home", label: "开始新项目", icon: MessageCirclePlus }, { key: "projects", label: "项目", icon: Boxes }, { key: "guide", label: "使用指南", icon: BookOpen }, { key: "settings", label: "设置", icon: Settings }] as const).map(({ key, label, icon: Icon }) =>
          <button key={key} className={"nav-item " + (view === key ? "nav-item-active" : "")} onClick={() => navigate(key)} aria-current={view === key ? "page" : undefined}><Icon size={18} /><span>{label}</span>{key === "projects" && <span className="nav-count">{projects.length}</span>}</button>)}
      </nav>
      <div className="sidebar-recent"><span className="sidebar-label">最近项目</span>{projects.slice(0, 5).map((project) => <button key={project.id} onClick={() => openProject(project)} className={selectedId === project.id ? "recent-active" : ""}><FileText size={15} /><span>{project.name}</span></button>)}{!projects.length && <p>你的项目会显示在这里</p>}</div>
      <div className="nav-footer"><span className={"connection connection-" + health}><i />{health === "ok" ? "服务已连接" : health === "down" ? "服务未连接" : "连接中"}</span><span className="sidebar-label">个人工作空间</span></div>
    </aside>
    <section className="main-content">
      <header className="topbar"><span>{title}</span><div className="topbar-actions"><button className="text-button" onClick={() => navigate("guide")}><CircleHelp size={16} />使用指南</button><button className="icon-button" aria-label="刷新数据" title="刷新数据" onClick={() => void refresh()} disabled={loading}><RefreshCw size={16} className={loading ? "animate-spin" : ""} /></button></div></header>
      {notice && <div className={"notice " + (notice.error ? "notice-error" : "notice-ok")} role={notice.error ? "alert" : "status"}><span>{notice.text}</span><button className="icon-button" onClick={() => setNotice(null)} aria-label="关闭提示"><X size={15} /></button></div>}
      {createPending && <div className="notice notice-error" role="status"><span>创建结果待核对，暂不提交新项目。</span><button className="secondary-button" disabled={creating} onClick={() => void create()}><RefreshCw size={16} />核对创建结果</button></div>}

      {view === "home" && <section className="start-page" ref={homeRef}>
        <div className="start-content"><span className="start-mark"><Image src="/prodforge-logo.svg" alt="" width={112} height={112} priority /></span><h1>让产品想法，从这里开始</h1><p className="start-subtitle">一个想法，一份清晰可执行的产品方案。</p>
          <form className="idea-composer" onSubmit={create}><textarea aria-label="产品想法" placeholder="我想做一个……为谁解决什么问题？" value={idea} disabled={creating || createPending} onChange={(event) => setIdea(event.target.value)} onKeyDown={(event) => { if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return; event.preventDefault(); event.currentTarget.form?.requestSubmit(); }} maxLength={5000} required /><div className="composer-bottom"><label className="composer-goal"><Boxes size={16} /><select aria-label="项目目标" value={goal} disabled={creating || createPending} onChange={(event) => setGoal(event.target.value)}>{Object.entries(samples?.goal_types || goalNames).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label><button className="send-button" type="submit" aria-label="创建项目" title="创建项目" disabled={creating || createPending || !idea.trim()}>{creating ? <Loader2 size={20} className="animate-spin" /> : <ArrowUp size={20} />}</button></div></form>
          <div className="start-samples"><span>试试这些想法</span>{samples?.samples.map((sample) => <button key={sample.name} disabled={creating || createPending} onClick={() => setIdea(sample.idea)}><Plus size={14} />{sample.name}</button>)}</div>
          <button className="quick-guide" onClick={() => navigate("guide")}><BookOpen size={18} /><span><strong>第一次使用？</strong>查看从想法到交付的完整步骤</span><ArrowRight size={16} /></button>
        </div>
        <div className="process-preview">{["描述产品想法", "确认需求与方案", "生成项目资料"].map((label, index) => <div key={label}><span>0{index + 1}</span><p>{label}</p>{index < 2 && <ChevronRight size={15} />}</div>)}</div>
      </section>}

      {view === "projects" && !selectedProject && <section className="workspace-content">
        <div className="page-heading"><div><h1>我的项目 <span>{projects.length}</span></h1><p>每个想法的进展，都在这里。</p></div><button className="primary-button" disabled={creating || createPending} onClick={() => { setNewName(""); setCreateOpen(true); }}><Plus size={17} />新建项目</button></div>
        <div className="project-toolbar"><label className="search-field"><Search size={17} /><input aria-label="搜索项目" placeholder="搜索项目名称或想法" value={query} onChange={(event) => setQuery(event.target.value)} /></label><div className="toolbar-actions"><select className="filter-select" aria-label="筛选阶段" value={stage} onChange={(event) => setStage(event.target.value)}><option value="all">全部阶段</option>{Object.entries(stageNames).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><div className="view-switch"><button className={mode === "gallery" ? "selected" : ""} aria-label="画廊视图" title="画廊视图" aria-pressed={mode === "gallery"} onClick={() => setMode("gallery")}><Grid2X2 size={17} /></button><button className={mode === "list" ? "selected" : ""} aria-label="列表视图" title="列表视图" aria-pressed={mode === "list"} onClick={() => setMode("list")}><LayoutList size={17} /></button></div></div></div>
        {loading && !projects.length ? <div className="empty-state"><Loader2 className="animate-spin" />正在加载项目</div> : filtered.length ? <div className={mode === "gallery" ? "project-gallery" : "project-list"}>
          {filtered.map((project) => <article className="project-card" key={project.id}><div className="project-card-top"><span className="stage-chip">{stageNames[project.current_stage] || project.current_stage}</span><button className="icon-button delete-project" onClick={() => askDelete(project)} title={"删除项目：" + project.name} aria-label={"删除项目：" + project.name}><Trash2 size={16} /></button></div><button className="project-open" onClick={() => openProject(project)}><h2>{project.name}</h2><p>{project.idea}</p><div className="project-progress" aria-label={"当前阶段：" + (stageNames[project.current_stage] || project.current_stage)}>{stageKeys.map((key, index) => <i className={index <= stageKeys.indexOf(project.current_stage) ? "reached" : ""} key={key} />)}</div><div className="project-card-meta"><span>{goalNames[project.goal_type]} · {dateLabel(project.updated_at)} 更新</span><ArrowRight size={17} /></div></button></article>)}
        </div> : <div className="empty-state"><Boxes size={30} /><h2>{projects.length ? "没有找到匹配的项目" : "开始你的第一个项目"}</h2><p>{projects.length ? "更换关键词或阶段再试试。" : "描述一个想法，逐步整理成可交接的资料。"}</p><button className="secondary-button" onClick={() => projects.length ? (setQuery(""), setStage("all")) : navigate("home")}>{projects.length ? "清除筛选" : "开始新项目"}</button></div>}
      </section>}

      {view === "projects" && selectedProject && <section className="workspace-content project-detail"><button className="text-button back-button" onClick={() => navigate("projects")}><ArrowLeft size={16} />返回项目</button><div className="page-heading"><div><h1>{selectedProject.name}</h1><p>{selectedProject.idea}</p></div><button className="icon-button delete-project" title="删除当前项目" aria-label="删除当前项目" onClick={() => askDelete(selectedProject)}><Trash2 size={17} /></button></div><WorkflowPanel key={selectedProject.id} project={selectedProject} onChanged={refreshProjects} /></section>}

      {view === "guide" && <section className="workspace-content guide-page"><div className="page-heading"><div><h1>从一个想法，到一份交付</h1><p>按顺序完成以下步骤。每个阶段的内容确认后，再推进下一步。</p></div></div><div className="guide-layout"><ol className="guide-steps">{guideSteps.map(([label, description, result], index) => <li key={label}><span className="step-number">{String(index + 1).padStart(2, "0")}</span><div><h2>{label}</h2><p>{description}</p><span className="guide-result"><Check size={14} />{result}</span>{index === 0 && <button className="text-button" onClick={() => navigate("settings")}>前往设置<ArrowRight size={14} /></button>}{index === 1 && <button className="text-button" onClick={() => navigate("home")}>创建项目<ArrowRight size={14} /></button>}</div></li>)}</ol><aside className="guide-aside"><h2>开始前检查</h2><p><span className={settings?.configured ? "check-dot" : "waiting-dot"} />{settings?.configured ? "模型已配置" : "尚未配置模型"}</p><p><span className={health === "ok" ? "check-dot" : "waiting-dot"} />{health === "ok" ? "服务已连接" : "检查服务连接"}</p><hr /><h3>已有项目怎么继续？</h3><p>打开左侧「项目」或最近项目，在阶段标签中继续操作，已保存的内容会自动加载。</p><h3>怎么删除项目？</h3><p>点击项目右上角的删除图标，核对项目名称后确认。项目及关联资料将被永久删除；生成任务运行时需等待结束。</p><h3>生成失败怎么办？</h3><p>检查模型配置和错误提示，再重试当前操作。已保存的资料会保留。</p><button className="secondary-button" onClick={() => navigate("projects")}>打开项目<ArrowRight size={15} /></button></aside></div></section>}

      <div hidden={view !== "settings"}><SettingsPanel settings={settings} onSaved={(result) => { ++settingsGeneration.current; setSettings(result); setNotice({ error: false, text: "模型配置已保存。" }); }} /></div>

      {createOpen && <Dialog title="新建项目" onClose={() => !creating && setCreateOpen(false)}><form className="create-form" onSubmit={create}><label className="form-label">项目名称<input className="field" value={newName} disabled={creating || createPending} onChange={(event) => setNewName(event.target.value)} required maxLength={200} placeholder="给你的项目起个名字" /></label><label className="form-label">产品想法<textarea className="field" value={idea} disabled={creating || createPending} onChange={(event) => setIdea(event.target.value)} required maxLength={5000} rows={4} placeholder="为谁，解决什么问题？" /></label><label className="form-label">项目目标<select className="field" value={goal} disabled={creating || createPending} onChange={(event) => setGoal(event.target.value)}>{Object.entries(samples?.goal_types || goalNames).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>{notice?.error && <p role="alert" className="inline-error">{notice.text}</p>}<div className="dialog-actions"><button className="secondary-button" type="button" onClick={() => setCreateOpen(false)} disabled={creating}>取消</button><button className="primary-button" disabled={creating} type="submit">{creating ? <Loader2 size={16} className="animate-spin" /> : createPending ? <RefreshCw size={16} /> : <Plus size={16} />}{createPending ? "核对创建结果" : "创建项目"}</button></div></form></Dialog>}
      {deleteTarget && <Dialog title="删除这个项目？" onClose={() => !deleting && setDeleteTarget(null)}><div className="delete-content"><p className="delete-name">{deleteTarget.name}</p><p>项目中的需求问答、竞品证据、产品文档、研发任务及导出记录将一并永久删除，此操作无法撤销。</p>{deleteError && <p className="inline-error" role="alert">{deleteError}</p>}<div className="dialog-actions"><button className="secondary-button" onClick={() => setDeleteTarget(null)} disabled={deleting}>保留项目</button><button className="danger-button" onClick={() => void removeProject()} disabled={deleting}>{deleting ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}确认删除</button></div></div></Dialog>}
    </section>
  </main>;
}

function Dialog({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return <dialog aria-label={title} ref={dialog} className="app-dialog" onCancel={(event) => { event.preventDefault(); onClose(); }} onClick={(event) => { if (event.target === event.currentTarget) { const rect = event.currentTarget.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose(); } }}><div className="dialog-heading"><h2>{title}</h2><button className="icon-button" aria-label="关闭弹窗" onClick={onClose}><X size={18} /></button></div>{children}</dialog>;
}

function SettingsPanel({ settings, onSaved }: { settings: ModelSettings | null; onSaved: (settings: ModelSettings) => void }) {
  const [form, setForm] = useState({ model_api_key: "", model_name: settings?.model_name || "qwen-plus", model_base_url: settings?.model_base_url || "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const dirty = useRef(false);
  const saveLock = useRef(false);
  useEffect(() => { if (settings && !dirty.current) setForm((current) => ({ ...current, model_name: settings.model_name, model_base_url: settings.model_base_url })); }, [settings]);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saveLock.current) return;
    saveLock.current = true; setSaving(true); setError("");
    try {
      const result = await api.saveModelSettings(form);
      dirty.current = false;
      setForm({ model_api_key: "", model_name: result.model_name, model_base_url: result.model_base_url });
      onSaved(result);
    }
    catch (error) { setError(errorText(error)); }
    finally { saveLock.current = false; setSaving(false); }
  }
  return <section className="workspace-content settings-page"><div className="page-heading"><div><h1>模型连接</h1><p>配置产品生成流程使用的模型服务。</p></div><span className="stage-chip">{settings?.configured ? "已配置" : "待配置"}</span></div><form className="settings-form" onSubmit={save} onChange={() => { dirty.current = true; }}><label className="form-label">API Key<input className="field" type="password" autoComplete="new-password" required disabled={saving} value={form.model_api_key} placeholder={settings?.configured ? "已保存密钥；修改配置时请重新填写" : "输入模型服务商提供的密钥"} onChange={(event) => setForm({ ...form, model_api_key: event.target.value })} /></label><label className="form-label">模型名称<input className="field" required disabled={saving} value={form.model_name} onChange={(event) => setForm({ ...form, model_name: event.target.value })} placeholder="例如 qwen-plus" /></label><label className="form-label">接口地址<input className="field" type="url" disabled={saving} value={form.model_base_url} onChange={(event) => setForm({ ...form, model_base_url: event.target.value })} placeholder="使用服务商提供的兼容接口地址" /></label>{error && <p role="alert" className="inline-error">{error}</p>}<button className="primary-button" type="submit" disabled={saving}>{saving ? <Loader2 className="animate-spin" size={16} /> : <Check size={16} />}保存配置</button></form></section>;
}
