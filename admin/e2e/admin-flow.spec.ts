import { readFileSync } from "node:fs";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { ADMIN_CSP } from "../tests/csp";

// Runs against the real local stack started by scripts\admin-e2e.ps1: owned PostgreSQL, seeded
// two-organization data, the control plane serving the production bundle and the fake gateway.
interface Credentials {
  organizations: Array<{
    slug: string;
    organization_id: string;
    gateway_key: string;
    accounts: Array<{ email: string; role: string; password: string }>;
  }>;
}

const file = process.env.FORGE_E2E_CREDENTIALS;
if (!file) throw new Error("FORGE_E2E_CREDENTIALS is not set: run scripts\\admin-e2e.ps1.");
const credentials = JSON.parse(readFileSync(file, "utf-8")) as Credentials;
const orgA = credentials.organizations.find((organization) => organization.slug === "org-a");
if (!orgA) throw new Error("The seeded organization org-a is missing from the credentials file.");
const admin = orgA.accounts.find((account) => account.role === "organization_admin");
const member = orgA.accounts.find((account) => account.role === "member");
if (!admin || !member) throw new Error("The seeded org-a accounts are missing from the credentials file.");

const NEWCOMER = { name: "Nina Newcomer", email: "nina.newcomer@forge.local.test" };

/** Records real CSP violations (browser events, not a replica of the policy) for the whole page life. */
async function watchViolations(page: Page) {
  await page.addInitScript(() => {
    (window as unknown as { __csp: string[] }).__csp = [];
    document.addEventListener("securitypolicyviolation", (event) =>
      (window as unknown as { __csp: string[] }).__csp.push(`${event.violatedDirective} ${event.blockedURI}`),
    );
  });
  return () => page.evaluate(() => (window as unknown as { __csp: string[] }).__csp);
}

/** The member's own view of the organization: what the client would be offered. */
async function memberView(request: APIRequestContext) {
  const login = await request.post("/forge/v1/accounts/login", { data: { email: member!.email, password: member!.password } });
  if (!login.ok()) return { status: login.status(), aliases: [] as string[] };
  const { access_token: token } = (await login.json()) as { access_token: string };
  const models = await request.get(`/forge/v1/orgs/${orgA!.organization_id}/models`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!models.ok()) return { status: models.status(), aliases: [] as string[] };
  const body = (await models.json()) as { models: Array<{ id: string }> };
  return { status: models.status(), aliases: body.models.map((item) => item.id) };
}

test("the control plane mounts the built admin under its real CSP", async ({ page }) => {
  const violations = await watchViolations(page);
  const failed: string[] = [];
  page.on("response", (response) => response.status() >= 400 && failed.push(`${response.status()} ${response.url()}`));
  page.on("requestfailed", (request) => failed.push(`failed ${request.url()}`));

  const response = await page.goto("/admin/");
  expect(response?.status()).toBe(200);
  expect(response?.headers()["content-security-policy"]).toBe(ADMIN_CSP);
  expect(response?.headers()["cache-control"]).toBe("no-store");
  await expect(page.getByRole("heading", { level: 1, name: "Prometheon Forge" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  // Self-hosted brand font really loaded from the same origin, not a fallback.
  await expect
    .poll(() =>
      page.evaluate(async () => {
        await document.fonts.ready;
        return [...document.fonts].some((face) => face.family.includes("Montserrat") && face.status === "loaded");
      }),
    )
    .toBe(true);
  expect(await violations()).toEqual([]);
  expect(failed).toEqual([]);

  // The policy is enforced by the browser, not just declared: an inline script must not run.
  await page.evaluate(() => {
    const script = document.createElement("script");
    script.textContent = "window.__injected = true";
    document.head.append(script);
  });
  expect(await page.evaluate(() => "__injected" in window)).toBe(false);
  expect(await violations()).toEqual([expect.stringContaining("script-src")]);
});

test("an admin invites a member, suspends access, sees the platform-managed gateway and publishes the catalog", async ({
  page,
  request,
}) => {
  const violations = await watchViolations(page);
  await page.goto("/admin/");

  await test.step("sign in as the seeded org-a administrator", async () => {
    await page.getByLabel("Email").fill(admin!.email);
    await page.getByLabel("Password").fill(admin!.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Organization A" })).toBeVisible();
  });

  await test.step("invite a member and see the pending invitation", async () => {
    await page.getByRole("button", { name: "Members" }).click();
    await expect(page.getByRole("cell", { name: member!.email })).toBeVisible();
    await page.getByRole("button", { name: "Invite member" }).click();
    await page.getByLabel("Name").fill(NEWCOMER.name);
    await page.getByLabel("Email").fill(NEWCOMER.email);
    await page.getByRole("button", { name: "Send invitation" }).click();
    await expect(page.getByRole("status")).toHaveText(`Invitation sent to ${NEWCOMER.email}.`);
    const pending = page.getByRole("row", { name: new RegExp(NEWCOMER.email) });
    await expect(pending).toContainText("Invited");
  });

  await test.step("suspend and reactivate the seeded member", async () => {
    const row = page.getByRole("row", { name: new RegExp(member!.email) });
    await row.getByRole("button", { name: /^Suspend/ }).click();
    // Suspending is destructive, so the page asks first.
    await page.getByRole("alertdialog").getByRole("button", { name: "Suspend", exact: true }).click();
    await expect(row).toContainText("Suspended");
    // The server, not the page, denies a suspended member.
    expect((await memberView(request)).status).not.toBe(200);
    await row.getByRole("button", { name: /^Reactivate/ }).click();
    await expect(row).toContainText("Active");
  });

  await test.step("see the gateway key as platform-managed and read-only", async () => {
    await page.getByRole("button", { name: "Gateway" }).click();
    await expect(page.getByText("Configured", { exact: true })).toBeVisible();
    await expect(page.getByText("Usable platform keys: 1")).toBeVisible();
    await expect(page.getByLabel("API key")).toHaveCount(0);
    expect(await page.content()).not.toContain(orgA!.gateway_key);
  });

  await test.step("refresh the models from the gateway and publish a catalog", async () => {
    await page.getByRole("button", { name: "Catalog" }).click();
    await expect(page.getByText("Not published")).toBeVisible();
    expect((await memberView(request)).aliases).toEqual([]);
    await page.getByRole("button", { name: "Refresh models" }).click();
    for (const upstream of ["fake-fast", "fake-slow", "fake-error", "fake-malformed", "fake-nousage"]) {
      await expect(page.getByLabel(`Alias for ${upstream}`, { exact: true })).toBeVisible();
    }
    await page.getByLabel("Publish fake-error", { exact: true }).uncheck();
    await page.getByLabel("Publish fake-malformed", { exact: true }).uncheck();
    await page.getByLabel("Publish fake-nousage", { exact: true }).uncheck();
    await page.getByLabel("Alias for fake-fast", { exact: true }).fill("fast");
    await page.getByLabel("Alias for fake-slow", { exact: true }).fill("slow");
    await page.getByLabel("Default: fake-fast", { exact: true }).check();
    await page.getByRole("button", { name: "Publish catalog" }).click();
    await expect(page.getByRole("status")).toHaveText("Published 2 aliases.");
    await expect(page.getByText("Default model: fast")).toBeVisible();
    await expect(page.getByRole("list", { name: "Published aliases" }).getByRole("listitem")).toHaveText(["fast", "slow"]);
  });

  await test.step("the member sees exactly the published aliases", async () => {
    expect(await memberView(request)).toEqual({ status: 200, aliases: ["fast", "slow"] });
  });

  await test.step("nothing sensitive lands in browser storage and sign-out ends the session", async () => {
    const stored = await page.evaluate(() => ({
      local: localStorage.length,
      session: sessionStorage.length,
      cookie: document.cookie,
    }));
    expect(stored).toEqual({ local: 0, session: 0, cookie: "" });
    expect(await violations()).toEqual([]); // the reload below starts a fresh page and a fresh record
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });

  expect(await violations()).toEqual([]);
});
