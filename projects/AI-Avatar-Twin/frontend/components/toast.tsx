'use client';

import { createContext, useContext, useState, useCallback, ReactNode } from 'react';

interface Toast {
  id: number;
  type: 'success' | 'error';
  message: string;
}

const ToastContext = createContext<{ show: (type: 'success' | 'error', message: string) => void }>({
  show: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const show = useCallback((type: 'success' | 'error', message: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, type, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3000);
  }, []);

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      <div style={{ position: 'fixed', top: 16, right: 16, zIndex: 100, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {toasts.map((t) => (
          <div
            key={t.id}
            style={{
              background: t.type === 'success' ? 'var(--success)' : 'var(--danger)',
              color: '#fff',
              padding: '10px 16px',
              borderRadius: 8,
              fontSize: 14,
              boxShadow: 'var(--shadow)',
              maxWidth: 320,
            }}
          >
            {t.type === 'success' ? '✓ ' : '✗ '}{t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
