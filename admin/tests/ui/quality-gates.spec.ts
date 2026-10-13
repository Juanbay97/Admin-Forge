import { expect, test } from "./support";
import { expectAccessible, expectNoCspViolations, expectNoHorizontalScroll, viewports } from "./quality";

test.describe("CSP gate", () => {
  test.use({ enforceCsp: false });

  test("reports a style element injected at runtime", async ({ page, adminUrl, csp }) => {
    await page.goto(adminUrl);
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    expectNoCspViolations(csp);
    await page.evaluate(() => {
      const style = document.createElement("style");
      style.textContent = "body { outline: 1px solid red; }";
      document.head.appendChild(style);
    });
    await expect.poll(() => csp.violations.length).toBeGreaterThan(0);
    expect(() => expectNoCspViolations(csp)).toThrow(/style-src/);
  });

  test("a clean page records nothing", async ({ page, adminUrl, csp }) => {
    await page.goto(adminUrl);
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    expect(csp.violations).toHaveLength(0);
  });
});

test.describe("accessibility gate", () => {
  test("fails on a control without an accessible name and names the rule", async ({ page, adminUrl }) => {
    await page.goto(adminUrl);
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    await page.evaluate(() => {
      const button = document.createElement("button");
      button.id = "unnamed";
      document.body.appendChild(button);
    });
    await expect(expectAccessible(page)).rejects.toThrow(/button-name/);
  });

  test("passes on the sign-in page at every viewport without horizontal scroll", async ({ page, adminUrl }) => {
    for (const viewport of Object.values(viewports)) {
      await page.setViewportSize(viewport);
      await page.goto(adminUrl);
      await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
      await expectAccessible(page);
      await expectNoHorizontalScroll(page);
    }
  });
});