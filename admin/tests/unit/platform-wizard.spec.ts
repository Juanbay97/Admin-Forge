import { expect, test } from "@playwright/test";
import { runSaga, type Progress, type SagaInput, type SagaPorts } from "../../src/areas/platform/companies/wizard/saga";
import { adminSchema, companySchema, keysModelsSchema } from "../../src/areas/platform/companies/wizard/schema";

const input: SagaInput = {
  company: { slug: "initech", display_name: "Initech", department: "General", admin_email: "ada@initech.test", admin_name: "Ada Lovelace" },
  branding: { name: "Initech", loginCopy: "Hi", theme: { primary: "#0B1D26", accent: "#E07A2D", tint: "#E8DCC1", heading: "montserrat", body: "inter" }, assets: {} },
  keys: [{ key_id: "55555555-5555-4555-8555-555555555555", priority: 1, active: true }],
  models: ["gpt-4o"],
};

function ports(failures: Record<string, number> = {}) {
  const calls: string[] = [];
  const attempt = (name: string) => {
    calls.push(name);
    if ((failures[name] ?? 0) > 0) {
      failures[name] = failures[name]! - 1;
      throw new Error(`${name} failed`);
    }
  };
  const value: SagaPorts = {
    create: async (company) => (attempt("create"), { id: "33333333-3333-4333-8333-333333333333", slug: company.slug, display_name: company.display_name, active: true, invitation: { id: "i", expires_at: "x", delivery_state: "delivered", delivery_channel: "local_mailbox" } }),
    saveBranding: async () => attempt("branding"),
    assignKeys: async () => attempt("keys"),
    setModels: async () => attempt("models"),
  };
  return { value, calls };
}

test.describe("create-company saga", () => {
  test("runs the four steps in order and reports each as done", async () => {
    const { value, calls } = ports();
    const progress = await runSaga(value, input);
    expect(calls).toEqual(["create", "branding", "keys", "models"]);
    expect(progress.steps).toEqual({ company: "ok", branding: "ok", keys: "ok", models: "ok" });
    expect(progress.company?.slug).toBe("initech");
    expect(progress.invitation?.delivery_state).toBe("delivered");
    expect(progress.failed).toBeUndefined();
  });

  test("branding is optional: without it the step is skipped, not failed", async () => {
    const { value, calls } = ports();
    const progress = await runSaga(value, { ...input, branding: null });
    expect(calls).toEqual(["create", "keys", "models"]);
    expect(progress.steps.branding).toBe("skipped");
  });

  for (const [step, name, expected] of [
    ["company", "create", { company: "failed", branding: "pending", keys: "pending", models: "pending" }],
    ["branding", "branding", { company: "ok", branding: "failed", keys: "pending", models: "pending" }],
    ["keys", "keys", { company: "ok", branding: "ok", keys: "failed", models: "pending" }],
    ["models", "models", { company: "ok", branding: "ok", keys: "ok", models: "failed" }],
  ] as const) {
    test(`a failure at ${step} stops there, keeps what was done and leaves the rest pending`, async () => {
      const { value, calls } = ports({ [name]: 1 });
      const progress = await runSaga(value, input);
      expect(progress.steps).toEqual(expected);
      expect(progress.failed?.step).toBe(step);
      expect(calls.at(-1)).toBe(name);
    });

    test(`retrying after a failure at ${step} repeats only the failed and later steps`, async () => {
      const { value, calls } = ports({ [name]: 1 });
      const first = await runSaga(value, input);
      calls.length = 0;
      const second = await runSaga(value, input, first);
      expect(second.steps).toEqual({ company: "ok", branding: "ok", keys: "ok", models: "ok" });
      expect(second.failed).toBeUndefined();
      expect(calls).toEqual(["create", "branding", "keys", "models"].slice(["create", "branding", "keys", "models"].indexOf(name)));
      expect(second.company?.id).toBe("33333333-3333-4333-8333-333333333333");
    });
  }

  test("a retry that fails again keeps the earlier progress", async () => {
    const { value } = ports({ keys: 2 });
    const first: Progress = await runSaga(value, input);
    const second = await runSaga(value, input, first);
    expect(second.steps).toEqual({ company: "ok", branding: "ok", keys: "failed", models: "pending" });
  });
});

test.describe("wizard step schemas", () => {
  test("company: a name, a valid code and a first department", () => {
    expect(companySchema.safeParse({ name: "Initech", code: "initech", department: "General" }).success).toBe(true);
    for (const bad of [{ name: "", code: "initech", department: "General" }, { name: "Initech", code: "In", department: "General" }, { name: "Initech", code: "Init Tech", department: "General" }, { name: "Initech", code: "initech", department: "" }]) {
      expect(companySchema.safeParse(bad).success, JSON.stringify(bad)).toBe(false);
    }
  });
  test("first administrator: a real-looking email and a name", () => {
    expect(adminSchema.safeParse({ email: "ada@initech.test", name: "Ada" }).success).toBe(true);
    expect(adminSchema.safeParse({ email: "ada", name: "Ada" }).success).toBe(false);
    expect(adminSchema.safeParse({ email: "ada@initech.test", name: " " }).success).toBe(false);
  });
  test("keys and models: at least one of each", () => {
    expect(keysModelsSchema.safeParse({ keys: ["55555555-5555-4555-8555-555555555555"], models: ["gpt-4o"] }).success).toBe(true);
    expect(keysModelsSchema.safeParse({ keys: [], models: ["gpt-4o"] }).success).toBe(false);
    expect(keysModelsSchema.safeParse({ keys: ["55555555-5555-4555-8555-555555555555"], models: [] }).success).toBe(false);
  });
});