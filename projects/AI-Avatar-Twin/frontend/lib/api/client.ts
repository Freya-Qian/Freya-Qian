'use client';

// 集中 API 层：token 管理 + 统一错误归一化 + 类型定义

const TOKEN_KEY = 'avt_token';

export function getToken(): string {
  return typeof window !== 'undefined' ? sessionStorage.getItem(TOKEN_KEY) || '' : '';
}
export function setToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string>) };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (options.body && typeof options.body === 'string') headers['Content-Type'] = 'application/json';

  const res = await fetch(`/api/v1${path}`, { ...options, headers });
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* 非 JSON 响应 */
  }
  if (!res.ok) {
    const e = (data as { error?: { code?: string; message?: string } })?.error;
    throw new ApiError(res.status, e?.code || 'ERROR', e?.message || `请求失败（HTTP ${res.status}）`);
  }
  return data as T;
}

// ---------- 类型 ----------

export interface User {
  id: string;
  phone: string;
}
export interface Project {
  id: string;
  name: string;
  default_avatar_profile_id: string | null;
  status: string;
}
export interface Profile {
  id: string;
  project_id: string;
  name: string;
  avatar_type: string;
  template_id: number;
  voice_type: string;
  style_tags: string[];
  language: string;
  catchphrases: string[];
  banned_phrases: string[];
  topic_preferences: string[];
  platform_preferences: string[];
  video_ratio: string;
}
export interface Source {
  id: string;
  project_id: string;
  source_type: string;
  name: string;
  url: string;
  status: string;
}
export interface Item {
  id: string;
  source_type: string;
  source_name: string;
  original_url: string;
  title: string;
  summary: string;
  keywords: string[];
  credibility_score: number;
  video_potential_score: number;
  status: string;
}
export interface Topic {
  id: string;
  source_item_id: string;
  title: string;
  angle: string;
  one_liner: string;
  score: number;
  risk_level: string;
  risk_flags: string[];
  status: string;
}
export interface Script {
  id: string;
  topic_id: string;
  duration_target: number;
  platform: string;
  language: string;
  content: string;
  fact_claims: string[];
  risk_flags: string[];
  source_urls: string[];
  version: number;
  status: string;
}
export interface Video {
  id: string;
  script_id: string;
  status: string;
  video_url: string;
  cover_url: string;
  subtitle_url: string;
  export_package_url: string;
  error_message: string;
}
export interface TemplateAvatar {
  id: number;
  name: string;
  image_url: string;
}
const AVATAR_ASSET_VERSION = '20260923-selected-final';

export async function listTemplates() {
  const templates = await apiFetch<TemplateAvatar[]>('/templates');
  return templates.map((template) => ({
    ...template,
    image_url: `${template.image_url}${template.image_url.includes('?') ? '&' : '?'}v=${AVATAR_ASSET_VERSION}`,
  }));
}

// ---------- 账户 ----------

export function requestCode(phone: string) {
  return apiFetch<{ ok: boolean; dev_code?: string }>('/auth/code', {
    method: 'POST',
    body: JSON.stringify({ phone }),
  });
}
export function verifyCode(phone: string, code: string) {
  return apiFetch<{ token: string; user: User }>('/auth/verify', {
    method: 'POST',
    body: JSON.stringify({ phone, code }),
  });
}
export function logout() {
  return apiFetch<{ ok: boolean }>('/auth/logout', { method: 'POST' });
}
export function me() {
  return apiFetch<User>('/auth/me');
}

// ---------- 项目 / Profile / 信息源 ----------

export function listProjects() {
  return apiFetch<Project[]>('/projects');
}
export function createProject(name: string) {
  return apiFetch<Project>('/projects', { method: 'POST', body: JSON.stringify({ name }) });
}
export function deleteProject(id: string) {
  return apiFetch<{ ok: boolean }>(`/projects/${id}`, { method: 'DELETE' });
}
export function listProfiles(projectId: string) {
  return apiFetch<Profile[]>(`/projects/${projectId}/profiles`);
}
export function createProfile(projectId: string, body: Partial<Profile> & { name: string }) {
  return apiFetch<Profile>(`/projects/${projectId}/profiles`, { method: 'POST', body: JSON.stringify(body) });
}
export function updateProfile(id: string, body: Partial<Profile>) {
  return apiFetch<Profile>(`/profiles/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
}
export function deleteProfile(id: string) {
  return apiFetch<{ ok: boolean }>(`/profiles/${id}`, { method: 'DELETE' });
}
export function listSources() {
  return apiFetch<Source[]>('/sources');
}
export function createSource(body: { project_id: string; source_type: string; url?: string; content?: string }) {
  return apiFetch<Source>('/sources', { method: 'POST', body: JSON.stringify(body) });
}
export function fetchSource(id: string) {
  return apiFetch<Item[]>(`/sources/${id}/fetch`, { method: 'POST' });
}
export function deleteSource(id: string) {
  return apiFetch<{ ok: boolean }>(`/sources/${id}`, { method: 'DELETE' });
}

// ---------- 条目 / 选题 / 脚本 / 视频 ----------

export function listItems() {
  return apiFetch<Item[]>('/items');
}
export function summarizeItem(id: string) {
  return apiFetch<Item>(`/items/${id}/summarize`, { method: 'POST' });
}
export function deleteItem(id: string) {
  return apiFetch<{ ok: boolean }>(`/items/${id}`, { method: 'DELETE' });
}
export function createTopics(itemId: string) {
  return apiFetch<Topic[]>(`/items/${itemId}/topics`, { method: 'POST' });
}
export function listTopics() {
  return apiFetch<Topic[]>('/topics');
}
export function deleteTopic(id: string) {
  return apiFetch<{ ok: boolean }>(`/topics/${id}`, { method: 'DELETE' });
}
export function listScripts(projectId?: string) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
  return apiFetch<Script[]>(`/scripts${query}`);
}
export function deleteScript(id: string) {
  return apiFetch<{ ok: boolean }>(`/scripts/${id}`, { method: 'DELETE' });
}
export function listVideos() {
  return apiFetch<Video[]>('/videos');
}
export function getVideo(id: string) {
  return apiFetch<Video>(`/videos/${id}`);
}
export function createVideo(scriptId: string, avatarProfileId?: string) {
  return apiFetch<Video>(`/scripts/${scriptId}/videos`, {
    method: 'POST',
    body: JSON.stringify({ avatar_profile_id: avatarProfileId || null }),
  });
}
export function retryVideo(id: string) {
  return apiFetch<Video>(`/videos/${id}/retry`, { method: 'POST' });
}
export function deleteVideo(id: string) {
  return apiFetch<{ ok: boolean }>(`/videos/${id}`, { method: 'DELETE' });
}
export interface AgentEvent {
  type: 'start' | 'step' | 'tool_result' | 'done' | string;
  goal?: string;
  step?: number;
  thought?: string;
  action?: string;
  tool?: string;
  result?: unknown;
  status?: string;
  script?: { id?: string; content?: string; risk_flags?: string[]; source_urls?: string[] } | null;
  steps?: number;
}
export async function* streamAgent(goal: string, profileId?: string, projectId?: string): AsyncGenerator<AgentEvent> {
  const res = await fetch('/api/v1/agent/run', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${getToken()}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ goal, profile_id: profileId || null, project_id: projectId || null }),
  });
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => null);
    const e = (data as { error?: { code?: string; message?: string } })?.error;
    throw new ApiError(res.status, e?.code || 'ERROR', e?.message || '自动生成失败');
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split('\n\n');
    buf = parts.pop() || '';
    for (const p of parts) {
      const line = p.trim();
      if (!line.startsWith('data:')) continue;
      yield JSON.parse(line.slice(5)) as AgentEvent;
    }
  }
}
export function updateScript(id: string, content: string) {
  return apiFetch<Script>(`/scripts/${id}`, { method: 'PATCH', body: JSON.stringify({ content }) });
}
export function exportScript(id: string, format: 'md' | 'txt') {
  return apiFetch<{ content: string; format: string }>(`/scripts/${id}/export?format=${format}`);
}
export async function uploadProfilePhoto(profileId: string, file: File) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('consent', 'true');
  const res = await fetch(`/api/v1/profiles/${profileId}/photo`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
    body: fd,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const e = (data as { error?: { code?: string; message?: string } })?.error;
    throw new ApiError(res.status, e?.code || 'ERROR', e?.message || '上传失败');
  }
  return data as Profile;
}

// ---------- 媒体下载（带 token 取 blob）----------

export async function fetchBlob(path: string): Promise<string> {
  const res = await fetch(`/api/v1${path}`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new ApiError(res.status, 'ERROR', '加载失败');
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export async function download(path: string, filename: string) {
  const url = await fetchBlob(path);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function previewAvatar(profileId: string, refresh = false): Promise<string> {
  return fetchBlob(`/profiles/${profileId}/avatar-preview?v=${AVATAR_ASSET_VERSION}${refresh ? '&refresh=true' : ''}`);
}

export async function downloadText(content: string, filename: string, type = 'text/markdown;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------- 脚本 SSE 流式生成 ----------

export async function* streamScript(topicId: string): AsyncGenerator<{ delta?: string; script?: Script; error?: string }> {
  const res = await fetch(`/api/v1/topics/${topicId}/scripts`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok || !res.body) throw new ApiError(res.status, 'ERROR', '生成脚本失败');
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split('\n\n');
    buf = parts.pop() || '';
    for (const p of parts) {
      const line = p.trim();
      if (!line.startsWith('data:')) continue;
      const payload = JSON.parse(line.slice(5));
      yield payload;
    }
  }
}
