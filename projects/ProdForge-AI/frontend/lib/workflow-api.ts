import type { Brief, Competitor, DevTask, Evidence, Positioning, Prd, Project, Question, TaskOut } from "./types";

export function displayValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  return typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
}

export class WorkflowError extends Error {
  constructor(message: string, public status = 0, public code = "") {
    super(message);
    this.name = "WorkflowError";
  }
}

export function isDefiniteSubmissionRejection(error: unknown): boolean {
  // A request timeout may hide a committed task; preserve its uncertain state.
  return error instanceof WorkflowError && error.status >= 400 && error.status < 500 && error.status !== 408;
}

export function sameCompetitor(left: { name: string; url: string }, right: { name: string; url: string }): boolean {
  return left.name.trim().toLowerCase() === right.name.trim().toLowerCase()
    || (!!left.url && !!right.url && left.url.replace(/\/+$/, "") === right.url.replace(/\/+$/, ""));
}

export async function workflowRequest<T>(path: string, signal: AbortSignal, method = "GET", body?: unknown): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort(signal.reason);
  signal.addEventListener("abort", abort, { once: true });
  if (signal.aborted) abort();
  const timer = setTimeout(() => controller.abort(new Error("请求超时，请刷新查看结果后重试")), 30_000);
  try {
    const response = await fetch(`/api/v1${path}`, {
      method, signal: controller.signal, cache: "no-store",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const raw = await response.text();
    let data;
    try { data = raw ? JSON.parse(raw) : null; }
    catch { throw new WorkflowError(`接口返回非 JSON 内容（HTTP ${response.status}）`, response.status); }
    if (!response.ok) {
      const detail = Array.isArray(data?.detail)
        ? data.detail.map((item: { loc?: unknown; msg?: unknown }) => `${displayValue(item.loc)}: ${displayValue(item.msg)}`).join("\n")
        : displayValue(data?.detail);
      throw new WorkflowError(displayValue(data?.error?.message) || detail || `请求失败（HTTP ${response.status}）`, response.status, displayValue(data?.error?.code));
    }
    return data as T;
  } catch (error) {
    if (controller.signal.aborted) throw controller.signal.reason;
    throw error;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", abort);
  }
}

export const projectPath = (id: string) => `/projects/${encodeURIComponent(id)}`;

export async function deleteWorkflowCompetitor(projectId: string, competitorId: string, signal: AbortSignal): Promise<void> {
  const path = `${projectPath(projectId)}/competitors/${encodeURIComponent(competitorId)}`;
  let result: { deleted: string };
  try {
    result = await workflowRequest<{ deleted: string }>(path, signal, "DELETE");
  } catch (error) {
    if (!(error instanceof WorkflowError) || error.status !== 409 || !error.message.includes("证据已被下游内容引用")) throw error;
    await workflowRequest(`${path}/detach-references`, signal, "POST");
    result = await workflowRequest<{ deleted: string }>(path, signal, "DELETE");
  }
  if (result?.deleted !== competitorId) throw new WorkflowError("删除响应无法确认，请刷新核对竞品列表。");
}

export type WorkflowJob = { path: string; label: string; id?: string; payload?: { url: string; source_type: "官网" } };
export function evidenceFetchJob(competitorId: string, url: string): WorkflowJob {
  return { path: `/competitors/${encodeURIComponent(competitorId)}/evidences/fetch`, label: "抓取官网证据", payload: { url: validateEvidenceUrl(url), source_type: "官网" } };
}
export function parseWorkflowJob(raw: string | null): WorkflowJob | null {
  try {
    const job = JSON.parse(raw || "null");
    if (!job || typeof job.path !== "string" || typeof job.label !== "string" || (job.id !== undefined && (typeof job.id !== "string" || !job.id))) return null;
    const basic = ["/clarify/questions", "/brief", "/competitors", "/competitors/recommend", "/positioning", "/prd", "/tasks"].includes(job.path);
    if (!basic && !/^\/competitors\/[^/]+\/evidences\/fetch$/.test(job.path)) return null;
    return { path: job.path, label: job.label, ...(job.id ? { id: job.id } : {}), ...(!basic ? { payload: { url: validateEvidenceUrl(job.payload?.url ?? ""), source_type: "官网" as const } } : {}) };
  } catch { return null; }
}

export type EvidenceDraft = { source_url: string; structured_claim: string; evidence_type: string; raw_excerpt: string };
export type WorkflowDrafts = {
  answers: Record<string, string>;
  competitor: { name: string; url: string };
  evidences: Record<string, EvidenceDraft>;
};
export const emptyEvidenceDraft = (): EvidenceDraft => ({ source_url: "", structured_claim: "", evidence_type: "定位", raw_excerpt: "" });
export const emptyWorkflowDrafts = (): WorkflowDrafts => ({ answers: {}, competitor: { name: "", url: "" }, evidences: {} });

// Only form fields are persisted; model configuration and credentials are never included.
export function parseWorkflowDrafts(raw: string | null): WorkflowDrafts {
  const result = emptyWorkflowDrafts();
  if (!raw) return result;
  try {
    const data = JSON.parse(raw);
    if (!data || typeof data !== "object") return result;
    const text = (value: unknown) => typeof value === "string" ? value : "";
    if (data.answers && typeof data.answers === "object" && !Array.isArray(data.answers)) {
      result.answers = Object.fromEntries(Object.entries(data.answers).filter((entry): entry is [string, string] => typeof entry[1] === "string"));
    }
    result.competitor = { name: text(data.competitor?.name), url: text(data.competitor?.url) };
    if (data.evidences && typeof data.evidences === "object" && !Array.isArray(data.evidences)) {
      result.evidences = Object.fromEntries(Object.entries(data.evidences).filter(([, value]) => value && typeof value === "object").map(([id, value]) => {
        const fields = value as Record<string, unknown>;
        return [id, { source_url: text(fields.source_url), structured_claim: text(fields.structured_claim), evidence_type: text(fields.evidence_type) || "定位", raw_excerpt: text(fields.raw_excerpt) }];
      }));
    }
  } catch { /* Corrupt or obsolete session data must not block the workflow. */ }
  return result;
}

export type WorkflowData = {
  questions: Question[]; brief: Brief | null; competitors: Competitor[];
  evidences: Record<string, Evidence[]>; positioning: Positioning | null; prd: Prd | null; tasks: DevTask[];
  currentStage: string;
};

export type WorkflowDestination = { stage: string; action: string; label: string; reason: string };
export function workflowBlocker(stage: string, data: WorkflowData): WorkflowDestination | null {
  const order = ["clarify", "competitor", "position", "prd", "tasks", "package"];
  const index = order.indexOf(stage);
  if (index >= 1 && data.brief?.status !== "confirmed") {
    if (stage === "competitor" && data.brief?.status === "draft") return null;
    if (data.brief?.status === "stale") return { stage: "clarify", action: "brief-update", label: "去更新需求摘要", reason: "需求摘要需更新，请重新生成后再确认。" };
    return { stage: "clarify", action: data.brief ? "brief-confirm" : !data.questions.length ? "questions" : data.questions.some((q) => q.required && !q.answer.trim()) ? "answers" : "brief-generate", label: data.brief ? "去确认需求摘要" : "去完成需求澄清", reason: "待确认需求摘要：以最新版本为准，已有竞品和证据会保留。" };
  }
  if (index >= 2 && !data.competitors.length) return { stage: "competitor", action: "competitor-add", label: "去添加竞品", reason: "生成定位前，至少需要一个竞品及一张证据卡。" };
  if (index >= 2 && !Object.values(data.evidences).some((items) => items.length)) return { stage: "competitor", action: "stage", label: "去抓取竞品证据", reason: "生成定位前，请为竞品抓取官网或手动添加至少一张证据卡。" };
  if (index >= 3 && data.positioning?.status !== "confirmed") return data.positioning?.status === "stale"
    ? { stage: "position", action: "positioning-generate", label: "去更新产品定位", reason: "产品定位需更新，请重新生成后再确认。" }
    : { stage: "position", action: data.positioning ? "positioning-confirm" : "positioning-generate", label: data.positioning ? "去确认产品定位" : "去生成产品定位", reason: "产品定位尚未确认。" };
  if (index >= 4 && data.prd?.status !== "confirmed") return data.prd?.status === "stale"
    ? { stage: "prd", action: "prd-generate", label: "去更新 PRD", reason: "PRD 需更新，请重新生成后再确认。" }
    : { stage: "prd", action: data.prd ? "prd-confirm" : "prd-generate", label: data.prd ? "去确认 PRD" : "去生成 PRD", reason: "PRD 尚未确认。" };
  if (stage === "package" && data.currentStage !== "package") return { stage: "tasks", action: data.tasks.length >= 5 && data.tasks.some((task) => task.priority === "P0") ? "tasks-confirm" : "tasks-generate", label: "去完成研发任务确认", reason: "研发任务尚未确认；仍可导出已有内容。" };
  return null;
}

export async function loadWorkflow(id: string, signal: AbortSignal): Promise<WorkflowData> {
  const base = projectPath(id);
  async function optional<T>(path: string): Promise<T | null> {
    try { return await workflowRequest<T>(base + path, signal); }
    catch (error) {
      if (error instanceof WorkflowError && error.status === 404 && error.code === "NOT_FOUND") return null;
      throw error;
    }
  }
  const [questions, brief, competitors, positioning, prd, tasks, project] = await Promise.all([
    workflowRequest<Question[]>(`${base}/clarify/questions`, signal), optional<Brief>("/brief"),
    workflowRequest<Competitor[]>(`${base}/competitors`, signal), optional<Positioning>("/positioning"),
    optional<Prd>("/prd"), workflowRequest<DevTask[]>(`${base}/tasks`, signal),
    workflowRequest<Project>(base, signal),
  ]);
  const entries = await Promise.all(competitors.map(async (c) => [c.id, await workflowRequest<Evidence[]>(`${base}/competitors/${encodeURIComponent(c.id)}/evidences`, signal)] as const));
  return { questions, brief, competitors, positioning, prd, tasks, evidences: Object.fromEntries(entries), currentStage: project.current_stage };
}

function delay(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const abort = () => { clearTimeout(timer); signal.removeEventListener("abort", abort); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, ms);
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
  });
}

export async function pollWorkflowTask(id: string, projectId: string, signal: AbortSignal, onStatus: (task: TaskOut) => void): Promise<TaskOut> {
  const deadline = Date.now() + 180_000;
  while (Date.now() < deadline) {
    const task = await workflowRequest<TaskOut>(`/tasks/${encodeURIComponent(id)}`, signal);
    if (task.project_id !== projectId) throw new WorkflowError("任务不属于当前项目");
    onStatus(task);
    if (task.status === "success") return task;
    if (task.status === "failed") throw new WorkflowError(displayValue(task.error) || "生成任务失败", 0, "TASK_FAILED");
    if (!["queued", "processing"].includes(task.status)) throw new WorkflowError(`未知任务状态：${displayValue(task.status)}`);
    await delay(1500, signal);
  }
  throw new WorkflowError("等待超过 3 分钟；后台任务可能仍在运行，可以继续查询原任务。", 0, "POLL_TIMEOUT");
}

export const exportChannels = [
  { value: "markdown", label: "Markdown" },
  { value: "feishu_copy", label: "飞书文档（复制内容）" },
  { value: "github_issue", label: "GitHub Issue（复制内容）" },
] as const;
export type ExportChannel = typeof exportChannels[number]["value"];
export type MarkdownExport = { export_id: string; channel: ExportChannel; title: string; content: string };

export async function exportWorkflow(id: string, channel: ExportChannel, signal: AbortSignal): Promise<MarkdownExport> {
  if (!exportChannels.some((item) => item.value === channel)) throw new WorkflowError("不支持的导出格式");
  const result = await workflowRequest<MarkdownExport>(`${projectPath(id)}/export`, signal, "POST", { channel });
  if (result.channel !== channel || typeof result.title !== "string" || typeof result.content !== "string" || !result.content.trim()) {
    throw new WorkflowError("导出接口返回的格式或内容不正确");
  }
  return result;
}

export function validateEvidenceUrl(value: string): string {
  const input = value.trim();
  // Require explicit authority; URL alone repairs malformed values such as https:///example.com.
  if (!/^https?:\/\/[^/\s?#\\]+(?:[/?#]|$)/i.test(input) || /[\s\\]/.test(input)) {
    throw new WorkflowError("证据来源必须是包含主机名的 http/https 链接");
  }
  try {
    const url = new URL(input);
    if (!["http:", "https:"].includes(url.protocol) || !url.hostname) throw new Error();
  } catch { throw new WorkflowError("证据来源链接格式不正确，请检查主机名和端口"); }
  return input;
}
export type Recommendation = { name: string; url: string; positioning: string };
export function parseRecommendations(task: TaskOut): Recommendation[] {
  const data: unknown = JSON.parse(task.result_json);
  if (!data || typeof data !== "object" || !("competitors" in data) || !Array.isArray(data.competitors)) throw new WorkflowError("推荐结果格式不正确");
  return data.competitors.filter((item): item is Recommendation => !!item && typeof item.name === "string" && typeof item.url === "string" && typeof item.positioning === "string");
}
