import type { AssignmentEntry, CreatedCompany, NewCompany } from "../../../../api/platform";
import type { BrandingDocument } from "../../../../api/branding";

export type StepId = "company" | "branding" | "keys" | "models";
export type StepStatus = "pending" | "ok" | "failed" | "skipped";
const ORDER: StepId[] = ["company", "branding", "keys", "models"];

export interface SagaInput {
  company: NewCompany;
  /** Null keeps the default Prometheon look: the step is skipped. */
  branding: BrandingDocument | null;
  keys: AssignmentEntry[];
  models: string[];
}

export interface SagaPorts {
  create(company: NewCompany): Promise<CreatedCompany>;
  saveBranding(companyId: string, document: BrandingDocument): Promise<void>;
  assignKeys(companyId: string, entries: AssignmentEntry[]): Promise<void>;
  setModels(companyId: string, models: string[]): Promise<void>;
}

export interface Progress {
  steps: Record<StepId, StepStatus>;
  company?: { id: string; slug: string; display_name: string };
  invitation?: CreatedCompany["invitation"];
  failed?: { step: StepId; error: unknown };
}

export const initialProgress = (): Progress => ({ steps: { company: "pending", branding: "pending", keys: "pending", models: "pending" } });

/**
 * Creates the company and then applies branding, keys and models, one step at a time. A failure stops the run and keeps
 * everything already done, so `runSaga(..., previous)` repeats only the failed and later steps (the PUTs are idempotent).
 * The company itself exists on the server from the first step on, so a failed later step is finished from its detail page too.
 */
export async function runSaga(ports: SagaPorts, input: SagaInput, previous?: Progress): Promise<Progress> {
  const progress: Progress = previous ? { ...previous, steps: { ...previous.steps }, failed: undefined } : initialProgress();
  const done = (step: StepId) => progress.steps[step] === "ok" || progress.steps[step] === "skipped";

  const actions: Record<StepId, () => Promise<void>> = {
    company: async () => {
      const created = await ports.create(input.company);
      progress.company = { id: created.id, slug: created.slug, display_name: created.display_name };
      progress.invitation = created.invitation;
    },
    branding: async () => {
      if (!input.branding) return;
      await ports.saveBranding(progress.company!.id, input.branding);
    },
    keys: () => ports.assignKeys(progress.company!.id, input.keys),
    models: () => ports.setModels(progress.company!.id, input.models),
  };

  for (const step of ORDER) {
    if (done(step)) continue;
    if (step === "branding" && !input.branding) {
      progress.steps.branding = "skipped";
      continue;
    }
    try {
      await actions[step]();
      progress.steps[step] = "ok";
    } catch (error) {
      progress.steps[step] = "failed";
      progress.failed = { step, error };
      break;
    }
  }
  return progress;
}