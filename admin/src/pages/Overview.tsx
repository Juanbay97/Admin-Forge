import { Building2 } from "lucide-react";
import { useEffect, useReducer, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AccountApi, Organization } from "../api/account";
import { ApiError } from "../api/client";
import { ADMIN_ROLE } from "../auth/access";
import { NotFound } from "../components/NotFound";
import { initialScope, scopeReducer } from "../scope/orgScope";
import { Alert } from "../ui/Alert";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { PageHeader } from "../ui/PageHeader";
import { Skeleton, SkeletonText } from "../ui/Skeleton";
import { Stat } from "../ui/Stat";

interface OverviewProps {
  api: AccountApi;
  organization: Organization;
}

export function Overview({ api, organization }: OverviewProps) {
  const { t } = useTranslation(["company", "common"]);
  const [scope, dispatch] = useReducer(scopeReducer, initialScope);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const orgId = organization.id;
    dispatch({ type: "switch", orgId });
    api.departments(orgId).then(
      (departments) => dispatch({ type: "loaded", orgId, departments }),
      (failure: unknown) =>
        dispatch({ type: "failed", orgId, reason: failure instanceof ApiError && failure.status === 404 ? "not-found" : "error" }),
    );
  }, [api, organization.id, attempt]);

  if (scope.status === "not-found") return <NotFound />;
  const loading = scope.status === "idle" || scope.status === "loading";
  const isAdmin = organization.roles.includes(ADMIN_ROLE);
  return (
    <section className="flex flex-col gap-6">
      <PageHeader title={organization.display_name} description={t("overview.description")} />
      <section aria-label={t("overview.summary")}>
        <dl className="grid gap-4 sm:grid-cols-3">
          <Stat label={t("overview.departments")}>{loading ? <Skeleton className="h-6 w-10" /> : scope.departments.length}</Stat>
          <Stat label={t("overview.role")}>{isAdmin ? t("common:roles.administrator") : t("common:roles.member")}</Stat>
          <Stat label={t("overview.status")}>
            <Badge tone="success">{organization.status === "active" ? t("overview.active") : organization.status}</Badge>
          </Stat>
        </dl>
      </section>
      <Card>
        <CardHeader>
          <CardTitle>{t("overview.departments")}</CardTitle>
        </CardHeader>
        <CardContent>
          {scope.status === "error" && (
            <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => setAttempt((count) => count + 1)}>{t("common:actions.tryAgain")}</Button>}>
              {t("common:errors.generic")}
            </Alert>
          )}
          {loading && (
            <div role="status">
              <span className="sr-only">{t("overview.loadingDepartments")}</span>
              <SkeletonText lines={3} />
            </div>
          )}
          {scope.status === "ready" &&
            (scope.departments.length > 0 ? (
              <ul className="grid gap-2 sm:grid-cols-2">
                {scope.departments.map((department) => (
                  <li key={department.id} className="flex min-h-11 items-center gap-3 rounded-control border border-line bg-subtle px-3 text-body">
                    <Building2 aria-hidden="true" className="size-4 shrink-0 text-muted" />
                    {department.name}
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState icon={Building2} title={t("overview.emptyTitle")} hint={t("overview.emptyHint")} />
            ))}
        </CardContent>
      </Card>
    </section>
  );
}