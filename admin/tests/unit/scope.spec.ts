import { expect, test } from "@playwright/test";
import { initialScope, scopeReducer } from "../../src/scope/orgScope";

const A = "11111111-1111-4111-8111-111111111111";
const B = "22222222-2222-4222-8222-222222222222";
const LEGAL = { id: "d1", name: "Legal" };
const FINANCE = { id: "d2", name: "Finance" };

test.describe("organisation scope", () => {
  test("loading an organisation fills only that organisation", () => {
    let state = scopeReducer(initialScope, { type: "switch", orgId: A });
    expect(state).toEqual({ orgId: A, status: "loading", departments: [] });
    state = scopeReducer(state, { type: "loaded", orgId: A, departments: [LEGAL] });
    expect(state).toEqual({ orgId: A, status: "ready", departments: [LEGAL] });
  });

  test("switching clears the previous organisation before the next one loads", () => {
    const readyA = scopeReducer(
      scopeReducer(initialScope, { type: "switch", orgId: A }),
      { type: "loaded", orgId: A, departments: [LEGAL] },
    );
    const switched = scopeReducer(readyA, { type: "switch", orgId: B });
    expect(switched).toEqual({ orgId: B, status: "loading", departments: [] });
  });

  test("a late response for a previous organisation is ignored", () => {
    const loadingB = scopeReducer(
      scopeReducer(initialScope, { type: "switch", orgId: A }),
      { type: "switch", orgId: B },
    );
    const afterStale = scopeReducer(loadingB, { type: "loaded", orgId: A, departments: [LEGAL] });
    expect(afterStale).toBe(loadingB);
    const afterFresh = scopeReducer(afterStale, { type: "loaded", orgId: B, departments: [FINANCE] });
    expect(afterFresh.departments).toEqual([FINANCE]);
  });

  test("a not-found organisation shows no data and a generic status", () => {
    const loading = scopeReducer(initialScope, { type: "switch", orgId: A });
    expect(scopeReducer(loading, { type: "failed", orgId: A, reason: "not-found" })).toEqual({
      orgId: A,
      status: "not-found",
      departments: [],
    });
    expect(scopeReducer(loading, { type: "failed", orgId: A, reason: "error" }).status).toBe("error");
  });

  test("a failure for a stale organisation is ignored", () => {
    const loadingB = scopeReducer(initialScope, { type: "switch", orgId: B });
    expect(scopeReducer(loadingB, { type: "failed", orgId: A, reason: "not-found" })).toBe(loadingB);
  });
});
