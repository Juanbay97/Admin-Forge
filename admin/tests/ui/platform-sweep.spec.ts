import type { Page } from "@playwright/test";
import { expect, expectAccessible, expectNoCspViolations, expectNoHorizontalScroll, test, viewports } from "./support";
import { ACME, OWNER, installPlatform, newWorld } from "./platformSupport";

// Every platform route, light and dark, at the three viewports: axe, no horizontal scroll and (through the shared fixture) zero CSP
// violations. The CSP watch fails the test at teardown; the explicit call makes the intent visible here.
const ROUTES: Array<[string, string, RegExp]> = [
  ["overview", "platform", /Platform overview/],
  ["companies", "platform/companies", /Companies/],
  ["new company", "platform/companies/new", /Create a company/],
  ["company overview", `platform/companies/${ACME}`, /Acme Corp/],
  ["company branding", `platform/companies/${ACME}?tab=branding`, /Acme Corp/],
  ["company keys", `platform/companies/${ACME}?tab=keys`, /Acme Corp/],
  ["company models", `platform/companies/${ACME}?tab=models`, /Acme Corp/],
  ["company members", `platform/companies/${ACME}?tab=members`, /Acme Corp/],
  ["company usage", `platform/companies/${ACME}?tab=usage`, /Acme Corp/],
  ["keys", "platform/keys", /Gateway keys/],
  ["prices", "platform/prices", /Model prices/],
  ["audit", "platform/audit", /Audit log/],
];

async function signIn(page: Page, adminUrl: string, path: string) {
  const world = newWorld();
  world.mfa.verified = true;
  // The company's keys were discovered, so the Models tab is swept with its editor rather than the "refresh first" notice.
  world.catalogs[ACME]!.discovered = { ids: ["gpt-4o", "gpt-4o-mini"], at: "2026-10-14T12:00:00+00:00" };
  await installPlatform(page, world);
  await page.goto(adminUrl + path);
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Password").fill(OWNER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

for (const [name, path, heading] of ROUTES) {
  test(`${name}: axe, no horizontal scroll and no CSP violation in light and dark at 375, 768 and 1280`, async ({ page, adminUrl, csp }) => {
    test.setTimeout(120_000);
    await signIn(page, adminUrl, path);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: /Loading/ })).toHaveCount(0, { timeout: 8000 }); // loading notices gone (an informational status may stay)
    for (const dark of [false, true]) {
      if (dark) await page.getByRole("button", { name: "Switch to dark mode" }).click();
      for (const size of Object.values(viewports)) {
        await page.setViewportSize(size);
        await expectNoHorizontalScroll(page);
        await expectAccessible(page, { exclude: ['[aria-label$="preview"]'] });
      }
    }
    expectNoCspViolations(csp);
  });
}