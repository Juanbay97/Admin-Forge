import { useQueryClient } from "@tanstack/react-query";
import { Check, CircleDashed, Loader2, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { draftToDocument, type Draft } from "../../../../brand/branding";
import { ApiError } from "../../../../api/client";
import { errorMessage } from "../../../../shell/errors";
import { useServices } from "../../../../shell/services";
import { Alert } from "../../../../ui/Alert";
import { Button, buttonVariants } from "../../../../ui/Button";
import { Card } from "../../../../ui/Card";
import { PageHeader } from "../../../../ui/PageHeader";
import { initialProgress, runSaga, type Progress, type SagaPorts, type StepId, type StepStatus } from "./saga";
import type { AdminStep, CompanyStep } from "./schema";
import { AdminStepForm, BrandingStepForm, CompanyStepForm, KeysStepForm } from "./steps";

const STEPS = ["Company", "Branding", "First admin", "Gateway keys", "Review"] as const;
const LABELS: Record<StepId, string> = { company: "Company", branding: "Branding", keys: "Gateway keys" };

interface State {
  company: CompanyStep | null;
  branding: Draft | null;
  admin: AdminStep | null;
  keys: string[];
}

function Stepper({ current }: { current: number }) {
  return (
    <ol aria-label="Steps" className="flex flex-wrap gap-x-6 gap-y-2">
      {STEPS.map((label, index) => (
        <li key={label} aria-current={index === current ? "step" : undefined} className="flex items-center gap-2 text-body aria-[current=step]:font-semibold aria-[current=step]:text-fg">
          <span className={index < current ? "flex size-6 items-center justify-center rounded-full bg-action text-caption text-on-action" : index === current ? "flex size-6 items-center justify-center rounded-full border-2 border-action text-caption text-fg" : "flex size-6 items-center justify-center rounded-full border border-line-strong text-caption text-muted"}>
            {index < current ? <Check aria-hidden="true" className="size-3.5" /> : index + 1}
          </span>
          <span className={index === current ? "" : "text-muted"}>{label}</span>
        </li>
      ))}
    </ol>
  );
}

const ICON: Record<StepStatus | "running", { icon: typeof Check; label: string }> = {
  ok: { icon: Check, label: "Done" },
  skipped: { icon: Check, label: "Skipped (default look)" },
  failed: { icon: TriangleAlert, label: "Failed" },
  pending: { icon: CircleDashed, label: "Waiting" },
  running: { icon: Loader2, label: "Working…" },
};

export function Wizard() {
  const { platform } = useServices();
  const client = useQueryClient();
  const [index, setIndex] = useState(0);
  const [state, setState] = useState<State>({ company: null, branding: null, admin: null, keys: [] });
  const [progress, setProgress] = useState<Progress | null>(null);
  const [running, setRunning] = useState(false);

  const ports: SagaPorts = useMemo(
    () => ({
      create: (company) => platform.createCompany(company),
      async saveBranding(id, document) {
        const current = await platform.branding(id);
        await platform.saveBranding(id, current.revision, document);
      },
      async assignKeys(id, entries) {
        await platform.assignKeys(id, entries);
      },
    }),
    [platform],
  );

  async function create(previous?: Progress) {
    if (!state.company || !state.admin) return;
    setRunning(true);
    setProgress(previous ?? initialProgress());
    const result = await runSaga(
      ports,
      {
        company: { slug: state.company.code, display_name: state.company.name.trim(), department: state.company.department.trim(), admin_email: state.admin.email.trim(), admin_name: state.admin.name.trim() },
        branding: state.branding ? draftToDocument(state.branding) : null,
        keys: state.keys.map((key_id, order) => ({ key_id, priority: order + 1, active: true })),
      },
      previous,
    );
    setProgress(result);
    setRunning(false);
    void client.invalidateQueries({ queryKey: ["platform", "companies"] });
  }

  const finished = progress && !progress.failed && Object.values(progress.steps).every((status) => status === "ok" || status === "skipped");
  const failed = progress?.failed;
  const conflict = failed?.step === "company" && failed.error instanceof ApiError && failed.error.code === "COMPANY_CONFLICT";

  let body;
  if (finished && progress.company) {
    const delivered = progress.invitation?.delivery_state === "delivered";
    body = (
      <div className="flex flex-col gap-4">
        <h2 className="font-title text-section font-semibold text-fg">{progress.company.display_name} is ready</h2>
        <p className="text-body text-muted">Company code: <code className="rounded-control bg-subtle px-2 py-1 font-mono text-fg">{progress.company.slug}</code></p>
        {delivered ? (
          <Alert tone="success">Invitation sent to {state.admin?.email}</Alert>
        ) : (
          <Alert tone="warning" title="The invitation email could not be sent">The company exists. Share the company code and ask {state.admin?.email} to use a password reset, or contact support to resend the invitation.</Alert>
        )}
        <div className="flex flex-wrap gap-3">
          <Link to={`/platform/companies/${progress.company.id}`} className={buttonVariants({})}>Open company</Link>
          <Link to="/platform/companies" className={buttonVariants({ variant: "outline" })}>Back to companies</Link>
        </div>
      </div>
    );
  } else if (progress) {
    body = (
      <div className="flex flex-col gap-4">
        <h2 className="font-title text-section font-semibold text-fg">Creating {state.company?.name}</h2>
        <ul aria-label="Setup steps" className="divide-y divide-line rounded-card border border-line">
          {(Object.keys(LABELS) as StepId[]).map((step) => {
            const status = running && progress.steps[step] === "pending" && (step === "company" || progress.steps[(Object.keys(LABELS) as StepId[])[(Object.keys(LABELS) as StepId[]).indexOf(step) - 1]!] !== "pending") ? "running" : progress.steps[step];
            const { icon: Icon, label } = ICON[status];
            return (
              <li key={step} className="flex items-center gap-3 px-4 py-3 text-body">
                <Icon aria-hidden="true" className={status === "failed" ? "size-5 text-danger" : status === "running" ? "size-5 animate-spin text-muted" : "size-5 text-muted"} />
                <span className="font-medium text-fg">{LABELS[step]}</span>
                <span className="ml-auto text-muted">{label}</span>
              </li>
            );
          })}
        </ul>
        {failed && (
          <Alert tone="destructive" title={`${LABELS[failed.step]} could not be set up`}>
            {failed.step === "company" ? errorMessage(failed.error) : `The company exists. ${errorMessage(failed.error)} Retry the failed steps, or finish setup from the company page.`}
          </Alert>
        )}
        {failed && (
          <div className="flex flex-wrap gap-3">
            {conflict ? <Button onClick={() => { setProgress(null); setIndex(0); }}>Change the company code</Button> : <Button loading={running} onClick={() => void create(progress)}>Retry failed steps</Button>}
            {progress.company && <Link to={`/platform/companies/${progress.company.id}`} className={buttonVariants({ variant: "outline" })}>Open company</Link>}
          </div>
        )}
      </div>
    );
  } else if (index === 0) {
    body = <CompanyStepForm value={state.company} onNext={(company) => { setState((current) => ({ ...current, company })); setIndex(1); }} />;
  } else if (index === 1) {
    body = <BrandingStepForm value={state.branding} onBack={() => setIndex(0)} onNext={(branding) => { setState((current) => ({ ...current, branding })); setIndex(2); }} />;
  } else if (index === 2) {
    body = <AdminStepForm value={state.admin} onBack={() => setIndex(1)} onNext={(admin) => { setState((current) => ({ ...current, admin })); setIndex(3); }} />;
  } else if (index === 3) {
    body = <KeysStepForm keys={state.keys} onBack={() => setIndex(2)} onNext={(keys) => { setState((current) => ({ ...current, keys })); setIndex(4); }} />;
  } else {
    body = (
      <div className="flex flex-col gap-4">
        <h2 className="font-title text-section font-semibold text-fg">Review and create</h2>
        <section aria-label="Summary">
          <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-[10rem_1fr]">
            <dt className="text-muted">Company</dt><dd className="font-medium text-fg">{state.company?.name}</dd>
            <dt className="text-muted">Code</dt><dd className="font-mono text-fg">{state.company?.code}</dd>
            <dt className="text-muted">First department</dt><dd className="text-fg">{state.company?.department}</dd>
            <dt className="text-muted">Branding</dt><dd className="text-fg">{state.branding ? `Custom: ${state.branding.name}` : "Default Prometheon look"}</dd>
            <dt className="text-muted">First administrator</dt><dd className="text-fg">{state.admin?.name} · {state.admin?.email}</dd>
            <dt className="text-muted">Gateway keys</dt><dd className="text-fg">{state.keys.length}</dd>
          </dl>
        </section>
        <div className="flex justify-between gap-3 pt-2">
          <Button variant="outline" onClick={() => setIndex(3)}>Back</Button>
          <Button loading={running} onClick={() => void create()}>Create company</Button>
        </div>
      </div>
    );
  }

  return (
    <section className="flex flex-col gap-6">
      <PageHeader title="Create a company" description="Name it, brand it, give it gateway keys and invite its first administrator." />
      <Stepper current={progress ? 4 : index} />
      <Card className="max-w-3xl">
        <div className="flex flex-col gap-4 p-5 sm:p-6">
          {!progress && index < 4 && <h2 className="font-title text-section font-semibold text-fg">{["Company", "Branding", "First administrator", "Gateway keys"][index]}</h2>}
          {body}
        </div>
      </Card>
    </section>
  );
}