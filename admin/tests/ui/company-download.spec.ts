import { readFileSync } from "node:fs";
import type { Page } from "@playwright/test";
import { ADMIN_BACKEND, expect, expectAccessible, expectNoHorizontalScroll, installBackend, ORG_A, test, viewports } from "./support";

const WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36";
const fixture = (name: string): string => readFileSync(new URL(`../fixtures/portal/${name}.json`, import.meta.url), "utf8");
const ENTRY = "Download Prometheon Forge";
const STAMPED = "MZ stamped installer stand-in";
// The sidebar has an entry named like the page; the big button is the one inside <main>.
const bigButton = (page: Page) => page.getByRole("main").getByRole("button", { name: ENTRY });

async function signIn(page: Page, adminUrl: string, email: string, options: { manifest?: boolean } = {}) {
  const backend = await installBackend(page, ADMIN_BACKEND);
  const configRequests: Array<{ search: string; authorization: string | undefined }> = [];
  const stampedRequests: Array<{ search: string; authorization: string | undefined }> = [];
  await page.route("**/forge/v1/downloads/company*", (route) => {
    stampedRequests.push({ search: new URL(route.request().url()).search, authorization: route.request().headers()["authorization"] });
    return route.fulfill({ status: 200, contentType: "application/octet-stream", headers: { "Content-Disposition": 'attachment; filename="Prometheon-Forge-Setup-org-a.exe"' }, body: STAMPED });
  });
  await page.route("**/downloads/latest.json", (route) =>
    options.manifest === false ? route.fulfill({ status: 404, body: "" }) : route.fulfill({ status: 200, contentType: "application/json", body: fixture("manifest") }),
  );
  await page.route("**/forge/v1/capabilities/installer-config*", (route) => {
    configRequests.push({ search: new URL(route.request().url()).search, authorization: route.request().headers()["authorization"] });
    return route.fulfill({ status: 200, contentType: "application/json", body: fixture("installer-config") });
  });
  await page.goto(adminUrl);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Sign in" }).click();
  return { backend, configRequests, stampedRequests };
}

const nav = (page: Page) => page.getByRole("navigation", { name: "Sections" });

test.describe("download area for every role", () => {
  test.use({ userAgent: WINDOWS });

  test("a company administrator finds it in the navigation and on the dashboard with the installer facts", async ({ page, adminUrl }) => {
    await signIn(page, adminUrl, "admin@example.com");
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();
    await expect(nav(page).getByRole("button", { name: ENTRY })).toBeVisible();
    const card = page.getByRole("region", { name: ENTRY });
    await expect(card).toContainText("v1.2.3");
    await expect(card).toContainText("86 MB");
    await card.getByRole("link", { name: /Download and set up/ }).click();
    await expect(page).toHaveURL(/\/admin\/company\/download$/);
    await expect(page.getByRole("heading", { level: 1, name: ENTRY })).toBeVisible();
    await expect(nav(page).getByRole("button", { name: ENTRY })).toHaveAttribute("aria-current", "page");
    await expect(bigButton(page)).toBeVisible();
    await expect(page.getByRole("link", { name: "Download for Windows" })).toHaveCount(0);
    await expect(page.getByText(/v1\.2\.3 .+ 86 MB/)).toBeVisible();
    await expect(page.getByTestId("sha256")).toHaveText("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
    await expect(page.getByTestId("company-code")).toHaveText("org-a");
    await expect(page.getByRole("heading", { name: /Install/ })).toBeVisible();
    await expect(page.getByText("SmartScreen")).toBeVisible();
  });

  test("the big button saves the installer named for this company from the stamped route", async ({ page, adminUrl }) => {
    const { stampedRequests } = await signIn(page, adminUrl, "admin@example.com");
    await nav(page).getByRole("button", { name: ENTRY }).click();
    const waiting = page.waitForEvent("download");
    await bigButton(page).click();
    const download = await waiting;
    expect(download.suggestedFilename()).toBe("Prometheon-Forge-Setup-org-a.exe");
    expect(readFileSync((await download.path())!, "utf8")).toBe(STAMPED);
    expect(stampedRequests).toEqual([{ search: `?org=${ORG_A}`, authorization: "Bearer token-admin-secret" }]);
  });

  test("the configuration button, under Advanced, saves forge-install.json from the installer-config route for this company", async ({ page, adminUrl }) => {
    const { configRequests } = await signIn(page, adminUrl, "admin@example.com");
    await nav(page).getByRole("button", { name: ENTRY }).click();
    await expect(page.getByRole("button", { name: "Download configuration (forge-install.json)" })).toBeHidden();
    await page.getByText("Advanced", { exact: true }).click();
    const waiting = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download configuration (forge-install.json)" }).click();
    const download = await waiting;
    expect(download.suggestedFilename()).toBe("forge-install.json");
    const file = JSON.parse(readFileSync((await download.path())!, "utf8")) as { schema: string; policy_keys: { keys: unknown[] } };
    expect(file.schema).toBe("forge.installer-config.v1");
    expect(configRequests).toEqual([{ search: `?org=${ORG_A}`, authorization: "Bearer token-admin-secret" }]);
  });

  test("a plain member sees the same entry in the navigation, on the dashboard and on its page", async ({ page, adminUrl }) => {
    await signIn(page, adminUrl, "member@example.com");
    await expect(page.getByRole("heading", { level: 1, name: /Welcome/ })).toBeVisible();
    await expect(nav(page).getByRole("button", { name: ENTRY })).toBeVisible();
    const card = page.getByRole("region", { name: ENTRY });
    await expect(card).toContainText("v1.2.3");
    await nav(page).getByRole("button", { name: ENTRY }).click();
    await expect(page).toHaveURL(/\/admin\/portal\/download$/);
    await expect(bigButton(page)).toBeVisible();
    await page.getByText("Advanced", { exact: true }).click();
    await expect(page.getByRole("button", { name: "Download configuration (forge-install.json)" })).toBeVisible();
  });

  test("with no installer published the entry stays and explains it, on both dashboards and the page", async ({ page, adminUrl }) => {
    await signIn(page, adminUrl, "admin@example.com", { manifest: false });
    await expect(page.getByRole("region", { name: ENTRY })).toContainText("not published yet");
    await nav(page).getByRole("button", { name: ENTRY }).click();
    await expect(page.getByText("The installer is not available yet")).toBeVisible();
    await expect(bigButton(page)).toHaveCount(0);
  });

  test("is accessible and fits every viewport", async ({ page, adminUrl }) => {
    await signIn(page, adminUrl, "admin@example.com");
    await expect(page.getByRole("region", { name: ENTRY })).toBeVisible();
    await expectAccessible(page);
    await nav(page).getByRole("button", { name: ENTRY }).click();
    await expect(page.getByRole("heading", { level: 1, name: ENTRY })).toBeVisible();
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});
