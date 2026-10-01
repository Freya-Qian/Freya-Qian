import type {
  Brief,
  Competitor,
  DecisionLog,
  DevTask,
  Feedback,
  ModelSettings,
  Positioning,
  Prd,
  Project,
  Question,
  SamplesResponse,
} from "./types";

type ApiErrorPayload = {
  error?: {
    code?: string;
    message?: string;
  };
  detail?: string | { loc?: (string | number)[]; msg?: string }[];
};

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  init?.signal?.addEventListener("abort", abort, { once: true });
  if (init?.signal?.aborted) abort();
  const timer = setTimeout(abort, 30_000);
  try {
    const response = await fetch(path, {
      ...init,
      signal: controller.signal,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
    const raw = await response.text();
    let data: ApiErrorPayload | T;
    try { data = JSON.parse(raw); }
    catch { throw new ApiError("服务返回了无法识别的响应，请核对操作结果。", "INVALID_RESPONSE", response.status); }
    if (!response.ok) {
      const error = data as ApiErrorPayload;
      throw new ApiError(
        error?.error?.message ?? (typeof error?.detail === "string" ? error.detail : error?.detail?.map((item) => `${item.loc?.filter((part) => part !== "body").join(".") || "输入"}: ${item.msg || "格式不正确"}`).join("；")) ?? `请求失败（${response.status}）`,
        error?.error?.code ?? "HTTP_ERROR",
        response.status,
      );
    }
    return data as T;
  } catch (error) {
    if (controller.signal.aborted) throw new ApiError("请求超时或已取消，请核对操作结果。", "TIMEOUT", 0);
    if (error instanceof ApiError) throw error;
    throw new ApiError("网络连接中断，请核对操作结果。", "NETWORK", 0);
  } finally {
    clearTimeout(timer);
    init?.signal?.removeEventListener("abort", abort);
  }
}

type ProjectCreate = { name: string; idea: string; goal_type: string };
type PendingCreate = { payload: ProjectCreate; existingIds: string[] };
const pendingCreateKey = "project-create-pending:v1";
let pendingCreate: PendingCreate | null = null;
let createInFlight: Promise<Project> | null = null;

export function getPendingProjectCreate(): PendingCreate | null {
  if (pendingCreate) return pendingCreate;
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(pendingCreateKey);
    if (!raw) return null;
    const saved = JSON.parse(raw) as PendingCreate;
    if (!saved || !Array.isArray(saved.existingIds) || !saved.existingIds.every((id) => typeof id === "string") ||
        !saved.payload || ![saved.payload.name, saved.payload.idea, saved.payload.goal_type].every((value) => typeof value === "string")) throw new Error();
    pendingCreate = saved;
    return saved;
  } catch { throw new ApiError("无法读取待核对的创建记录，请保留当前页面并检查浏览器存储。", "CREATE_UNCERTAIN", 0); }
}

function clearPendingCreate() {
  if (typeof window !== "undefined") sessionStorage.removeItem(pendingCreateKey);
  pendingCreate = null;
}

export async function reconcileProjectCreate(): Promise<Project> {
  const pending = getPendingProjectCreate();
  if (!pending) throw new ApiError("没有待核对的创建请求。", "INVALID_INPUT", 400);
  const projects = await api.projects();
  const matches = projects.filter((project) => !pending.existingIds.includes(project.id) &&
    project.name === pending.payload.name && project.idea === pending.payload.idea && project.goal_type === pending.payload.goal_type);
  // An absent result cannot prove that an interrupted POST will not commit later.
  if (matches.length !== 1) throw new ApiError("创建结果尚不能唯一确认。请稍后核对；不会重复提交创建请求。", "CREATE_UNCERTAIN", 0);
  clearPendingCreate();
  return matches[0];
}

async function createProject(payload: ProjectCreate): Promise<Project> {
  if (getPendingProjectCreate()) return reconcileProjectCreate();
  const existing = await api.projects();
  const pending = { payload, existingIds: existing.map((project) => project.id) };
  // Persist before submitting so a browser refresh cannot turn a retry into another POST.
  if (typeof window !== "undefined") {
    try { sessionStorage.setItem(pendingCreateKey, JSON.stringify(pending)); }
    catch { throw new ApiError("浏览器无法保存创建记录，尚未提交。请恢复会话存储后重试。", "STORAGE_UNAVAILABLE", 0); }
  }
  pendingCreate = pending;
  let project: Project;
  try {
    project = await request<Project>("/api/v1/projects", { method: "POST", body: JSON.stringify(payload) });
    if (!project || typeof project.id !== "string" || project.name !== payload.name || project.idea !== payload.idea || project.goal_type !== payload.goal_type) {
      throw new ApiError("创建响应不完整，正在核对结果。", "INVALID_RESPONSE", 200);
    }
  } catch (error) {
    if (error instanceof ApiError && error.status >= 400 && error.status < 500 && ![408, 425, 429].includes(error.status) && error.code !== "INVALID_RESPONSE") {
      clearPendingCreate();
      throw error;
    }
    try { return await reconcileProjectCreate(); }
    catch { throw new ApiError("创建结果待核对，请点击核对创建结果。不会再次提交创建请求。", "CREATE_UNCERTAIN", 0); }
  }
  clearPendingCreate();
  return project;
}

async function deleteProject(id: string): Promise<{ deleted: string }> {
  const path = `/api/v1/projects/${encodeURIComponent(id)}`;
  try {
    const result = await request<{ deleted: string }>(path, { method: "DELETE" });
    if (result?.deleted !== id) throw new ApiError("删除响应不完整。", "INVALID_RESPONSE", 200);
    return result;
  }
  catch (error) {
    if (isMissingResource(error)) return { deleted: id };
    if (error instanceof ApiError && error.status >= 400 && error.status < 500 && ![408, 425, 429].includes(error.status) && error.code !== "INVALID_RESPONSE") throw error;
    try { await request<Project>(path); }
    catch (lookupError) { if (isMissingResource(lookupError)) return { deleted: id }; }
    throw new ApiError("删除结果尚未确认。可刷新列表核对，或重试删除。", "DELETE_UNCERTAIN", 0);
  }
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  samples: () => request<SamplesResponse>("/api/v1/samples"),
  projects: () => request<Project[]>("/api/v1/projects"),
  project: (id: string) => request<Project>(`/api/v1/projects/${id}`),
  createProject: (payload: ProjectCreate): Promise<Project> => {
    if (!createInFlight) createInFlight = createProject(payload).finally(() => { createInFlight = null; });
    return createInFlight;
  },
  deleteProject,
  modelSettings: () => request<ModelSettings>("/api/v1/settings/model"),
  saveModelSettings: (payload: { model_api_key: string; model_name?: string; model_base_url?: string }) =>
    request<ModelSettings>("/api/v1/settings/model", { method: "PUT", body: JSON.stringify(payload) }),
  questions: (projectId: string) => request<Question[]>(`/api/v1/projects/${projectId}/clarify/questions`),
  brief: (projectId: string) => request<Brief>(`/api/v1/projects/${projectId}/brief`),
  competitors: (projectId: string) => request<Competitor[]>(`/api/v1/projects/${projectId}/competitors`),
  positioning: (projectId: string) => request<Positioning>(`/api/v1/projects/${projectId}/positioning`),
  prd: (projectId: string) => request<Prd>(`/api/v1/projects/${projectId}/prd`),
  devTasks: (projectId: string) => request<DevTask[]>(`/api/v1/projects/${projectId}/tasks`),
  decisions: (projectId: string) => request<DecisionLog[]>(`/api/v1/projects/${projectId}/decisions`),
  feedback: (projectId: string) => request<Feedback[]>(`/api/v1/projects/${projectId}/feedback`),
};

export function isMissingResource(error: unknown) {
  return error instanceof ApiError && error.status === 404;
}
