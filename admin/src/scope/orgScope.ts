import type { Department } from "../api/account";

export interface ScopeState {
  orgId: string | null;
  status: "idle" | "loading" | "ready" | "not-found" | "error";
  departments: Department[];
}

export type ScopeAction =
  | { type: "switch"; orgId: string }
  | { type: "loaded"; orgId: string; departments: Department[] }
  | { type: "failed"; orgId: string; reason: "not-found" | "error" };

export const initialScope: ScopeState = { orgId: null, status: "idle", departments: [] };

/** Everything shown for an organisation lives here; a switch discards it all first. */
export function scopeReducer(state: ScopeState, action: ScopeAction): ScopeState {
  if (action.type === "switch") return { orgId: action.orgId, status: "loading", departments: [] };
  if (action.orgId !== state.orgId) return state; // a late reply for an organisation we left
  if (action.type === "loaded") return { orgId: state.orgId, status: "ready", departments: action.departments };
  return { orgId: state.orgId, status: action.reason, departments: [] };
}