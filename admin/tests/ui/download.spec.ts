import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { readFileSync } from "node:fs";
import type { Page } from "@playwright/test";
import { MEMBER, ORG, STAMPED_BYTES, newPortalWorld } from "./portalSupport";
import { joinAndLand } from "./portalSession";


// The sidebar also has an entry named like the page; the big button is the one inside <main>.
const bigButton = (page: Page) => page.getByRole("main").getByRole("button", { name: "Download Prometheon Forge" });

const WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36";

test.describe("download page", () => {
  test.use({ userAgent: WINDOWS });

  test("shows one big download button, the company code, the installer facts, the hash and the install steps", async ({ page, adminUrl }) => {
    await joinAndLand(page, adminUrl);
    await expect(page.getByRole("heading", { level: 1, name: "Download Prometheon Forge" })).toBeVisible();
    await expect(page.getByTestId("company-code")).toHaveText("acme");
    await expect(bigButton(page)).toBeVisible();
    await expect(page.getByRole("link", { name: "Download for Windows" })).toHaveCount(0);
    await expect(page.locator('a[href*="/downloads/"]')).toHaveCount(0);
    await expect(page.getByText(/v1\.2\.3 .+ 86 MB/)).toBeVisible();
    await expect(page.getByText("Released Oct 1, 2026")).toBeVisible();
    await expect(page.getByTestId("sha256")).toHaveText("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
    await expect(page.getByRole("heading", { name: /Install/ })).toBeVisible();
    await expect(page.getByText("SmartScreen")).toBeVisible();
  });

  test("the button saves the installer named for the company, fetched with the session for the chosen company", async ({ page, adminUrl }) => {
    const { requests } = await joinAndLand(page, adminUrl);
    const waiting = page.waitForEvent("download");
    await bigButton(page).click();
    const download = await waiting;
    expect(download.suggestedFilename()).toBe("Prometheon-Forge-Setup-acme.exe");
    expect(readFileSync((await download.path())!, "utf8")).toBe(STAMPED_BYTES);
    const asked = requests.find((request) => request.path === "/forge/v1/downloads/company");
    expect(asked?.search).toBe(`?org=${ORG}`);
    expect(asked?.authorization).toBe(`Bearer ${MEMBER.token}`);
    await expect(bigButton(page)).toBeEnabled();
  });

  test("a download that cannot be prepared is explained and can be retried", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.stamped = null;
    await joinAndLand(page, adminUrl, world);
    await bigButton(page).click();
    await expect(page.getByText("The download could not be prepared")).toBeVisible();
    await expect(bigButton(page)).toBeEnabled();
  });
  test("the deep link carries the origin and the code, and the manual fallback is always visible", async ({ page, adminUrl }) => {
    await joinAndLand(page, adminUrl);
    const open = page.getByRole("link", { name: "Open Forge" });
    const href = (await open.getAttribute("href")) ?? "";
    expect(href).toBe(`prometheon-forge://join?cp=${encodeURIComponent(new URL(page.url()).origin)}&code=acme`);
    await expect(page.getByText("Not opening? Enter code")).toBeVisible();
    await expect(page.getByText("SmartScreen")).toBeVisible();
  });

  test("the configuration file is an Advanced option, closed by default", async ({ page, adminUrl }) => {
    await joinAndLand(page, adminUrl);
    const configuration = page.getByRole("button", { name: "Download configuration (forge-install.json)" });
    await expect(page.getByText("Advanced", { exact: true })).toBeVisible();
    await expect(configuration).toBeHidden();
    await page.getByText("Advanced", { exact: true }).click();
    await expect(configuration).toBeVisible();
  });

  test("downloads the installer configuration of the chosen company", async ({ page, adminUrl }) => {
    const { requests } = await joinAndLand(page, adminUrl);
    await page.getByText("Advanced", { exact: true }).click();
    const waiting = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download configuration (forge-install.json)" }).click();
    const download = await waiting;
    expect(download.suggestedFilename()).toBe("forge-install.json");
    const file = JSON.parse(readFileSync((await download.path())!, "utf8")) as { company_code: string; policy_keys: { keys: Array<{ status: string }> } };
    expect(file.company_code).toBe("acme");
    expect(file.policy_keys.keys.map((key) => key.status)).toEqual(["active", "retired"]);
    const asked = requests.find((request) => request.path === "/forge/v1/capabilities/installer-config");
    expect(asked?.search).toBe(`?org=${ORG}`);
    expect(asked?.authorization).toBe(`Bearer ${MEMBER.token}`);
  });

  test("a configuration that cannot be prepared is explained and can be retried", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.installer = null;
    await joinAndLand(page, adminUrl, world);
    await page.getByText("Advanced", { exact: true }).click();
    await page.getByRole("button", { name: "Download configuration (forge-install.json)" }).click();
    await expect(page.getByText("The configuration could not be prepared")).toBeVisible();
    await expect(page.getByRole("button", { name: "Download configuration (forge-install.json)" })).toBeEnabled();
  });
  test("copies the company code", async ({ page, adminUrl, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await joinAndLand(page, adminUrl);
    await page.getByRole("button", { name: "Copy code" }).click();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("acme");
  });

  test("an unpublished installer is explained and the code is still shown", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.manifest = null;
    await joinAndLand(page, adminUrl, world);
    await expect(page.getByText("The installer is not available yet")).toBeVisible();
    await expect(page.getByTestId("company-code")).toHaveText("acme");
    await expect(bigButton(page)).toHaveCount(0);
  });

  test("a manifest without a Windows installer reads as not published", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.manifest = { version: "1.0.0", released_at: "2026-10-01T00:00:00Z", platforms: {} };
    await joinAndLand(page, adminUrl, world);
    await expect(page.getByText("The installer is not available yet")).toBeVisible();
  });

  test("a manifest pointing off-origin is refused, never offered", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.manifest = { version: "1.0.0", released_at: "2026-10-01T00:00:00Z", platforms: { windows: { url: "https://evil.test/Forge.exe", sha256: "a".repeat(64), size_bytes: 1 } } };
    await joinAndLand(page, adminUrl, world);
    await expect(page.getByText("The installer is not available yet")).toBeVisible();
    await expect(page.locator('a[href*="evil.test"]')).toHaveCount(0);
  });

  test("is accessible and fits every viewport, light theme", async ({ page, adminUrl }) => {
    await joinAndLand(page, adminUrl);
    await expect(bigButton(page)).toBeVisible();
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});

test.describe("download page on another system", () => {
  test.use({ userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Safari/605.1.15" });
  test("says Windows only for now instead of offering a file that would not run", async ({ page, adminUrl }) => {
    await joinAndLand(page, adminUrl);
    await expect(page.getByText("Windows only for now")).toBeVisible();
    await expect(page.getByText(/You are on macOS/)).toBeVisible();
    await expect(bigButton(page)).toHaveCount(0);
    await expect(page.getByTestId("company-code")).toHaveText("acme");
  });
});
