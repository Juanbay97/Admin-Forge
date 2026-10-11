import type { Page } from "@playwright/test";
import { ADMIN_BACKEND, LOCAL, ORG_A, ORG_B, PROD, expect, installBackend, test } from "./support";

const KEY = "sk-live-super-secret-value";

async function openGateway(page: Page, adminUrl: string, email = "admin@example.com") {
  await page.goto(adminUrl);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Sign in" }).click();
  if (email === "multi@example.com") await page.getByLabel("Organization").selectOption({ label: "Org A" });
  await page.getByRole("button", { name: "Gateway" }).click();
}

test.describe("gateway settings", () => {
  test("offers only the allow-listed base URLs and starts unconfigured", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await openGateway(page, adminUrl);
    await expect(page.getByRole("heading", { level: 1, name: "Gateway" })).toBeVisible();
    await expect(page.getByText("Not configured")).toBeVisible();
    await expect(page.getByText("Revision 0")).toBeVisible();
    const endpoint = page.getByLabel("Gateway base URL");
    await expect(endpoint.locator("option")).toHaveText([PROD, LOCAL]);
    await expect(endpoint).toHaveValue(PROD);
  });

  test("the key is write-only: sent once, cleared, never rendered", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openGateway(page, adminUrl);
    const field = page.getByLabel("API key");
    await expect(field).toHaveAttribute("type", "password");
    await page.getByLabel("Gateway base URL").selectOption(LOCAL);
    await field.fill(KEY);
    await page.getByRole("button", { name: "Save key" }).click();

    await expect(page.getByText("Configured", { exact: true })).toBeVisible();
    await expect(page.getByText("Revision 1")).toBeVisible();
    await expect(field).toHaveValue("");
    await expect(page.getByLabel("Gateway base URL")).toHaveValue(LOCAL);
    expect(await page.content()).not.toContain(KEY);
    expect(api.stored(ORG_A)).toMatchObject({ savedKey: KEY, endpoint: LOCAL, revision: 1 });
    const writes = api.requests.filter((r) => r.method === "PUT");
    expect(writes.map((r) => r.path)).toEqual([`/forge/v1/orgs/${ORG_A}/gateway`]);
  });

  test("a stale revision shows a conflict and overwrites nothing", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openGateway(page, adminUrl);
    await expect(page.getByText("Revision 0")).toBeVisible();
    api.bumpGateway(ORG_A); // someone else saved in the meantime
    await page.getByLabel("API key").fill(KEY);
    await page.getByRole("button", { name: "Save key" }).click();
    await expect(page.getByRole("alert")).toHaveText(
      "The gateway configuration was changed by someone else. Reload to see the latest version; nothing was overwritten.",
    );
    expect(api.stored(ORG_A)?.savedKey).toBeUndefined();
    await expect(page.getByLabel("API key")).toHaveValue("");

    await page.getByRole("button", { name: "Reload" }).click();
    await expect(page.getByText("Revision 1")).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
    await page.getByLabel("API key").fill(KEY);
    await page.getByRole("button", { name: "Save key" }).click();
    await expect(page.getByText("Revision 2")).toBeVisible();
    expect(api.stored(ORG_A)?.savedKey).toBe(KEY);
  });

  test("a rejected key keeps the page and shows a redacted error", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openGateway(page, adminUrl);
    await page.getByLabel("API key").fill("rejected-key");
    await page.getByRole("button", { name: "Save key" }).click();
    await expect(page.getByRole("alert")).toHaveText("The base URL or key was not accepted. Check them and try again.");
    await expect(page.getByText("Not configured")).toBeVisible();
    expect(await page.content()).not.toContain("rejected-key");
    expect(api.stored(ORG_A)?.savedKey).toBeUndefined();
  });

  test("a stale organization renders the generic not-found", async ({ page, adminUrl }) => {
    await installBackend(page, { ...ADMIN_BACKEND, gateways: {} });
    await openGateway(page, adminUrl);
    await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
    await expect(page.getByLabel("API key")).toHaveCount(0);
  });

  test("switching organizations clears the gateway before the next loads", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openGateway(page, adminUrl, "multi@example.com");
    await expect(page.getByText("Revision 0")).toBeVisible();
    api.hold(ORG_B);
    await page.getByLabel("Organization").selectOption({ label: "Org B" });
    await expect(page.getByRole("status")).toHaveText("Loading gateway…");
    await expect(page.getByText("Revision 0")).toHaveCount(0);
    api.letThrough(ORG_B);
    await expect(page.getByText("Revision 2")).toBeVisible();
    await expect(page.getByLabel("Gateway base URL")).toHaveValue(LOCAL);
    await expect(page.getByLabel("API key")).toHaveValue("");
  });
});

test.describe("accessibility", () => {
  test("saving works with the keyboard alone", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openGateway(page, adminUrl);
    await page.getByLabel("Gateway base URL").focus();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("API key")).toBeFocused();
    await page.keyboard.type(KEY);
    await page.keyboard.press("Enter");
    await expect(page.getByText("Revision 1")).toBeVisible();
    expect(api.stored(ORG_A)?.savedKey).toBe(KEY);
  });

  test("honors prefers-reduced-motion", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await openGateway(page, adminUrl);
    const duration = () =>
      page.getByRole("button", { name: "Save key" }).evaluate((el) => getComputedStyle(el).transitionDuration);
    expect(await duration()).not.toBe("0s");
    await page.emulateMedia({ reducedMotion: "reduce" });
    expect(await duration()).toBe("0s");
  });
});
