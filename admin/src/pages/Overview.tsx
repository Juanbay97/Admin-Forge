import { useEffect, useReducer } from "react";
import type { AccountApi, Organization } from "../api/account";
import { ApiError } from "../api/client";
import { NotFound } from "../components/NotFound";
import { initialScope, scopeReducer } from "../scope/orgScope";

interface OverviewProps {
  api: AccountApi;
  organization: Organization;
}

export function Overview({ api, organization }: OverviewProps) {
  const [scope, dispatch] = useReducer(scopeReducer, initialScope);

  useEffect(() => {
    const orgId = organization.id;
    dispatch({ type: "switch", orgId });
    api.departments(orgId).then(
      (departments) => dispatch({ type: "loaded", orgId, departments }),
      (failure: unknown) =>
        dispatch({ type: "failed", orgId, reason: failure instanceof ApiError && failure.status === 404 ? "not-found" : "error" }),
    );
  }, [api, organization.id]);

  if (scope.status === "not-found") return <NotFound />;
  return (
    <section className="flex flex-col gap-4">
      <h1 className="font-title text-2xl font-bold text-primary">{organization.display_name}</h1>
      <h2 className="font-title text-lg font-semibold">Departments</h2>
      {scope.status === "error" && <p role="alert">Something went wrong. Try again.</p>}
      {(scope.status === "idle" || scope.status === "loading") && <p role="status">Loading departments…</p>}
      {scope.status === "ready" &&
        (scope.departments.length > 0 ? (
          <ul className="list-disc pl-6">
            {scope.departments.map((department) => (
              <li key={department.id}>{department.name}</li>
            ))}
          </ul>
        ) : (
          <p>No departments yet.</p>
        ))}
    </section>
  );
}