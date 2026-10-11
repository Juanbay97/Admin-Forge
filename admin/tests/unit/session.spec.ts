import { expect, test } from "@playwright/test";
import { createSession } from "../../src/auth/session";

// Any storage touch is a failure: the bearer token lives in module memory only.
function forbidStorage() {
  const trap = () => {
    throw new Error("browser storage must never be used for credentials");
  };
  for (const name of ["localStorage", "sessionStorage", "indexedDB"]) {
    Object.defineProperty(globalThis, name, { configurable: true, get: trap });
  }
  return () => {
    for (const name of ["localStorage", "sessionStorage", "indexedDB"]) {
      delete (globalThis as Record<string, unknown>)[name];
    }
  };
}

test.describe("session", () => {
  test("holds the token in memory and clears it", () => {
    const release = forbidStorage();
    try {
      const session = createSession();
      expect(session.token()).toBeNull();
      session.set("token-one");
      expect(session.token()).toBe("token-one");
      session.set("token-two");
      expect(session.token()).toBe("token-two");
      session.clear();
      expect(session.token()).toBeNull();
    } finally {
      release();
    }
  });

  test("sessions are independent instances", () => {
    const first = createSession();
    const second = createSession();
    first.set("only-first");
    expect(second.token()).toBeNull();
    expect(first.token()).toBe("only-first");
  });

  test("notifies subscribers on change and stops after unsubscribe", () => {
    const session = createSession();
    const seen: Array<string | null> = [];
    const stop = session.subscribe(() => seen.push(session.token()));
    session.set("a");
    session.clear();
    stop();
    session.set("b");
    expect(seen).toEqual(["a", null]);
  });
});
