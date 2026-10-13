// Thirty minutes without a keystroke, pointer move or tap and the owner is signed out (company data is sensitive).
export const IDLE_LIMIT_MS = 30 * 60 * 1000;

interface IdleOptions {
  onIdle: () => void;
  set?: (run: () => void, ms: number) => unknown;
  clear?: (handle: unknown) => void;
}

export function createIdleTimer({ onIdle, set = (run, ms) => setTimeout(run, ms), clear = (handle) => clearTimeout(handle as number) }: IdleOptions) {
  let handle: unknown;
  const touch = () => {
    if (handle !== undefined) clear(handle);
    handle = set(onIdle, IDLE_LIMIT_MS);
  };
  const stop = () => {
    if (handle !== undefined) clear(handle);
    handle = undefined;
  };
  touch();
  return { touch, stop };
}