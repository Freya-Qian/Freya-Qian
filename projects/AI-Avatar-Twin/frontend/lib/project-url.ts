'use client';

const PROJECT_KEY = 'avt_project_id';
export const PROJECT_CHANGE_EVENT = 'avt:project-change';

export function getProjectFromUrl(): string {
  if (typeof window === 'undefined') return '';
  return new URLSearchParams(window.location.search).get('project') || '';
}

export function getRememberedProject(): string {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem(PROJECT_KEY) || '';
}

export function rememberProject(projectId: string) {
  if (typeof window === 'undefined' || !projectId) return;
  localStorage.setItem(PROJECT_KEY, projectId);
  const url = new URL(window.location.href);
  url.searchParams.set('project', projectId);
  window.history.replaceState(null, '', `${url.pathname}?${url.searchParams.toString()}`);
  window.dispatchEvent(new CustomEvent(PROJECT_CHANGE_EVENT, { detail: projectId }));
}

export function projectHref(path: string, projectId?: string) {
  if (!projectId) return path;
  return `${path}?project=${encodeURIComponent(projectId)}`;
}
