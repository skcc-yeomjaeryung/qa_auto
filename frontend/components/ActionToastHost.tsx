"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ACTION_TOAST_EVENT,
  type ActionToastInput,
  type ActionToastTone,
} from "../lib/actionToast";

type ActionToast = Required<Pick<ActionToastInput, "id" | "title" | "message">> & {
  tone: ActionToastTone;
  durationMs: number;
};

const DEFAULT_DURATION: Record<ActionToastTone, number> = {
  progress: 3600,
  success: 2800,
  error: 5200,
  info: 3200,
};

export function ActionToastHost() {
  const [toasts, setToasts] = useState<ActionToast[]>([]);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: string) => {
    const timer = timers.current.get(id);
    if (timer) clearTimeout(timer);
    timers.current.delete(id);
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  useEffect(() => {
    const activeTimers = timers.current;
    const onToast = (event: Event) => {
      const detail = (event as CustomEvent<ActionToastInput>).detail;
      if (!detail?.id || !detail.title || !detail.message) return;
      const tone = detail.tone || "info";
      const next: ActionToast = {
        id: detail.id,
        title: detail.title,
        message: detail.message,
        tone,
        durationMs: detail.durationMs ?? DEFAULT_DURATION[tone],
      };
      setToasts((current) => {
        const withoutCurrent = current.filter((toast) => toast.id !== next.id);
        return [...withoutCurrent, next].slice(-3);
      });
      const previousTimer = activeTimers.get(next.id);
      if (previousTimer) clearTimeout(previousTimer);
      activeTimers.set(next.id, setTimeout(() => dismiss(next.id), next.durationMs));
    };
    window.addEventListener(ACTION_TOAST_EVENT, onToast);
    return () => {
      window.removeEventListener(ACTION_TOAST_EVENT, onToast);
      activeTimers.forEach((timer) => clearTimeout(timer));
      activeTimers.clear();
    };
  }, [dismiss]);

  if (toasts.length === 0) return null;

  return (
    <section className="action-toast-region" aria-label="작업 알림" aria-live="polite" data-testid="action-toast-region">
      {toasts.map((toast) => (
        <article
          key={toast.id}
          className={`action-toast is-${toast.tone}`}
          role={toast.tone === "error" ? "alert" : "status"}
          data-toast-tone={toast.tone}
          data-testid="action-toast"
        >
          <span className="action-toast-symbol" aria-hidden>
            {toast.tone === "progress" ? <i /> : toast.tone === "success" ? "✓" : toast.tone === "error" ? "!" : "i"}
          </span>
          <div>
            <strong>{toast.title}</strong>
            <p>{toast.message}</p>
          </div>
          <button type="button" aria-label={`${toast.title} 알림 닫기`} onClick={() => dismiss(toast.id)}>×</button>
        </article>
      ))}
    </section>
  );
}
