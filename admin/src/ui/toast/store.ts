// A tiny external store for notifications: framework-free so its timing rules are unit-testable with a manual clock.
export type ToastTone = "info" | "success" | "warning" | "destructive";

export interface ToastInput {
  tone: ToastTone;
  title: string;
  message?: string;
  /** Milliseconds before it dismisses itself; 0 keeps it until dismissed. Defaults depend on the tone. */
  duration?: number;
}

export interface Toast extends ToastInput {
  id: string;
}

export interface ToastStore {
  push(input: ToastInput): string;
  dismiss(id: string): void;
  list(): readonly Toast[];
  subscribe(listener: () => void): () => void;
}

/** Failures stay on screen longest; confirmations are brief. */
export const DEFAULT_DURATION: Record<ToastTone, number> = { info: 4000, success: 4000, warning: 6000, destructive: 8000 };

type Schedule = (run: () => void, ms: number) => () => void;
const timeout: Schedule = (run, ms) => {
  const handle = setTimeout(run, ms);
  return () => clearTimeout(handle);
};

export function createToastStore({ schedule = timeout, limit = 4 }: { schedule?: Schedule; limit?: number } = {}): ToastStore {
  let toasts: readonly Toast[] = [];
  const listeners = new Set<() => void>();
  const timers = new Map<string, () => void>();
  let counter = 0;

  const change = (next: readonly Toast[]) => {
    toasts = next;
    listeners.forEach((listener) => listener());
  };
  const forget = (id: string) => {
    timers.get(id)?.();
    timers.delete(id);
  };
  const store: ToastStore = {
    push(input) {
      const id = `toast-${++counter}`;
      const kept = [...toasts, { ...input, id }];
      for (const dropped of kept.slice(0, Math.max(0, kept.length - limit))) forget(dropped.id);
      change(kept.slice(-limit));
      const duration = input.duration ?? DEFAULT_DURATION[input.tone];
      if (duration > 0) timers.set(id, schedule(() => store.dismiss(id), duration));
      return id;
    },
    dismiss(id) {
      forget(id);
      if (toasts.some((toast) => toast.id === id)) change(toasts.filter((toast) => toast.id !== id));
    },
    list: () => toasts,
    subscribe(listener) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
  };
  return store;
}