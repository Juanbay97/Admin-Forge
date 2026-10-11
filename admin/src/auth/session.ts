// The bearer token lives only in this module's memory: a reload means signing in again.
// It is deliberately never written to storage, cookies or the URL.
export interface Session {
  token(): string | null;
  set(token: string): void;
  clear(): void;
  subscribe(listener: () => void): () => void;
}

export function createSession(): Session {
  let current: string | null = null;
  const listeners = new Set<() => void>();
  const change = (next: string | null) => {
    current = next;
    listeners.forEach((listener) => listener());
  };
  return {
    token: () => current,
    set: (token) => change(token),
    clear: () => change(null),
    subscribe(listener) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
  };
}

export const session = createSession();