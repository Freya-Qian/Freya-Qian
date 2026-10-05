'use client';

import { useEffect, useId, useRef, type RefObject } from 'react';

export function ConfirmDialog({ open, title, description, busy, error, fallbackFocusRef, onConfirm, onCancel }: {
  open: boolean;
  title: string;
  description: string;
  busy: boolean;
  error?: string;
  fallbackFocusRef?: RefObject<HTMLElement | null>;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (!open) return;
    const dialog = ref.current!;
    const trigger = document.activeElement;
    const fallback = fallbackFocusRef?.current;
    dialog.showModal();
    return () => {
      dialog.close();
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus();
      else fallback?.focus();
    };
  }, [open, fallbackFocusRef]);

  return (
    <dialog ref={ref} className="confirm-dialog" aria-labelledby={titleId} aria-describedby={descriptionId}
      aria-busy={busy} onCancel={(event) => { event.preventDefault(); if (!busy) onCancel(); }}>
      <h2 id={titleId} className="confirm-dialog-title">{title}</h2>
      <p id={descriptionId} className="confirm-dialog-description">{description}</p>
      {error && <p className="err" role="alert">{error}</p>}
      <div className="confirm-dialog-actions">
        <button type="button" className="btn btn-ghost" autoFocus disabled={busy} onClick={onCancel}>取消</button>
        <button type="button" className="btn danger-btn" disabled={busy} onClick={onConfirm}>
          {busy ? '正在删除…' : '确认删除'}
        </button>
      </div>
    </dialog>
  );
}
