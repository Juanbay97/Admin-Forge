import { ADMIN_BACKEND, expect, installBackend, test } from "./support";
import { ADMIN_CSP } from "../csp";

const SECRETS = ["correct-horse-battery", "token-admin-secret"];

test.describe("no persisted credentials", () => {
  test("nothing secret reaches storage, cookies or the URL", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByLabel("Password").fill("correct-horse-battery");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();

    const snapshot = await page.evaluate(async () => ({
      local: JSON.stringify({ ...localStorage }),
      session: JSON.stringify({ ...sessionStorage }),
      databases: (await indexedDB.databases()).length,
      cookie: document.cookie,
      html: document.documentElement.outerHTML,
    }));
    expect(snapshot.local).toBe("{}");
    expect(snapshot.session).toBe("{}");
    expect(snapshot.databases).toBe(0);
    for (const secret of SECRETS) {
      expect(snapshot.cookie).not.toContain(secret);
      expect(snapshot.html).not.toContain(secret);
      expect(page.url()).not.toContain(secret);
    }
    // The shell redirects the root to the role home; the URL still carries no query, hash or credential.
    expect(page.url()).toBe(`${adminUrl}company`);
  });

  test("a reload requires signing in again", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByLabel("Password").fill("correct-horse-battery");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });
});

test.describe("offline, same-origin delivery", () => {
  test("renders with local fonts and no blocked or cross-origin request", async ({ page, context, origin, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    const foreign: string[] = [];
    await context.route((url) => url.origin !== origin, (route) => {
      foreign.push(route.request().url());
      return route.abort();
    });
    const violations: string[] = [];
    await page.exposeFunction("reportViolation", (directive: string) => violations.push(directive));
    await page.addInitScript(() => {
      document.addEventListener("securitypolicyviolation", (e) =>
        (window as unknown as { reportViolation: (d: string) => void }).reportViolation(e.violatedDirective),
      );
    });
    const fonts: string[] = [];
    page.on("response", (response) => {
      if (response.url().endsWith(".woff2")) fonts.push(`${response.status()} ${new URL(response.url()).pathname}`);
    });

    const landing = await page.goto(adminUrl);
    expect(landing?.headers()["content-security-policy"]).toBe(ADMIN_CSP);
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByLabel("Password").fill("correct-horse-battery");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();
    await page.evaluate(() => document.fonts.ready);

    expect(foreign).toEqual([]);
    expect(violations).toEqual([]);
    expect([...new Set(fonts)].sort()).toEqual([
      "200 /admin/fonts/inter-latin-wght-normal.woff2",
      "200 /admin/fonts/montserrat-latin-wght-normal.woff2",
    ]);
  });
});

test.describe("accessibility", () => {
  test("login completes with the keyboard alone", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await expect(page.getByLabel("Email")).toBeFocused();
    await page.keyboard.type("admin@example.com");
    await page.keyboard.press("Tab");
    await page.keyboard.type("correct-horse-battery");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();
  });

  test("honors prefers-reduced-motion", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    const duration = () =>
      page.getByRole("button", { name: "Sign in" }).evaluate((el) => getComputedStyle(el).transitionDuration);
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.goto(adminUrl);
    expect(await duration()).not.toBe("0s");
    await page.emulateMedia({ reducedMotion: "reduce" });
    expect(await duration()).toBe("0s");
  });
});
