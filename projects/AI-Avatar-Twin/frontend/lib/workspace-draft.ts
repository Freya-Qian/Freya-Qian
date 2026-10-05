'use client';

const DRAFT_PREFIX = 'avt_workspace_draft:v1';

function draftKey(scope: string, projectId: string) {
  return `${DRAFT_PREFIX}:${scope}:${projectId}`;
}

export function readWorkspaceDraft<T>(scope: string, projectId: string): T | null {
  if (typeof window === 'undefined' || !projectId) return null;
  try {
    const raw = localStorage.getItem(draftKey(scope, projectId));
    return raw ? JSON.parse(raw) as T : null;
  } catch {
    return null;
  }
}

export function saveWorkspaceDraft<T>(scope: string, projectId: string, data: T) {
  if (typeof window === 'undefined' || !projectId) return;
  localStorage.setItem(draftKey(scope, projectId), JSON.stringify(data));
}
