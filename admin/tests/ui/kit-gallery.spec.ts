import { contrastOfHex } from "../../src/brand/palette";
import { expect, expectAccessible, expectNoCspViolations, expectNoHorizontalScroll, test, viewports } from "./support";

test.describe("kit core gallery", () => {
  test.beforeEach(async ({ page, origin }) => {
    await page.emulateMedia({ reducedMotion: "reduce" }); // no colour transitions mid-measurement
    await page.goto(`${origin}/admin/?kit=core`);
    await expect(page.getByRole("heading", { level: 1, name: "Kit core" })).toBeVisible();
  });

  test("every button variant renders; disabled and loading buttons refuse clicks", async ({ page }) => {
    for (const name of ["Default", "Secondary", "Outline", "Ghost", "Destructive", "Link action"]) {
      await expect(page.getByRole("button", { name, exact: true })).toBeEnabled();
    }
    await expect(page.getByRole("button", { name: "Disabled" })).toBeDisabled();
    const saving = page.getByRole("button", { name: "Saving" });
    await expect(saving).toBeDisabled();
    await expect(saving).toHaveAttribute("aria-busy", "true");
    await expect(page.getByRole("link", { name: "Docs link" })).toHaveAttribute("href", "#docs");
  });

  test("keyboard focus shows a 2px ring", async ({ page }) => {
    await page.getByRole("button", { name: "Default", exact: true }).focus();
    await page.keyboard.press("Shift+Tab");
    await page.keyboard.press("Tab");
    const outline = await page.getByRole("button", { name: "Default", exact: true }).evaluate((element) => {
      const style = getComputedStyle(element);
      return { width: style.outlineWidth, style: style.outlineStyle };
    });
    expect(outline).toEqual({ width: "2px", style: "solid" });
  });

  test("interactive targets are at least 40px", async ({ page }) => {
    const targets = page.locator("main :is(button:visible:not(label button), a[href]:visible, input:visible, select:visible, textarea:visible, label:has([role])):not([aria-hidden=true])");
    const count = await targets.count();
    expect(count).toBeGreaterThan(15);
    const small: string[] = [];
    for (let index = 0; index < count; index++) {
      const box = await targets.nth(index).boundingBox();
      const label = (await targets.nth(index).innerText()).trim() || (await targets.nth(index).getAttribute("aria-label")) || `#${index}`;
      if (box && (box.height < 39.5 || (box.width < 39.5))) small.push(`${label} ${box.width}x${box.height}`);
    }
    expect(small).toEqual([]);
  });

  test("a company theme restyles the default button with no component edit", async ({ page }) => {
    await page.evaluate(() => document.documentElement.style.setProperty("--brand-teal", "#0B5FFF"));
    const colours = await page.getByRole("button", { name: "Default", exact: true }).evaluate((element) => {
      const style = getComputedStyle(element);
      return { background: style.backgroundColor, color: style.color };
    });
    expect(colours.background).toBe("rgb(11, 95, 255)");
    expect(colours.color).toBe("rgb(255, 255, 255)");
    expect(contrastOfHex("#0B5FFF", "#FFFFFF")).toBeGreaterThanOrEqual(4.5);
  });

  test("typography follows the scale: Montserrat 24/32 titles, Inter 14/20 body", async ({ page }) => {
    const title = await page.getByRole("heading", { level: 1 }).evaluate((element) => {
      const style = getComputedStyle(element);
      return { family: style.fontFamily, size: style.fontSize, line: style.lineHeight };
    });
    expect(title.family.startsWith('Montserrat')).toBe(true);
    expect([title.size, title.line]).toEqual(["24px", "32px"]);
    const body = await page.getByText("Plain body copy sits on a 14/20 scale.").evaluate((element) => {
      const style = getComputedStyle(element);
      return { family: style.fontFamily, size: style.fontSize, line: style.lineHeight };
    });
    expect(body.family.startsWith("Inter")).toBe(true);
    expect([body.size, body.line]).toEqual(["14px", "20px"]);
  });

  test("a field error is bound to its input and announced through a polite live region", async ({ page }) => {
    const email = page.getByLabel("Work email");
    await expect(email).not.toHaveAttribute("aria-invalid", "true");
    await email.fill("not-an-email");
    await email.blur();
    await expect(email).toHaveAttribute("aria-invalid", "true");
    const describedBy = await email.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    const region = page.locator(`[id="${describedBy!.split(" ").at(-1)}"]`);
    await expect(region).toHaveText("Enter a valid email address");
    await expect(region).toHaveAttribute("aria-live", "polite");
    await email.fill("pat@example.com");
    await expect(email).not.toHaveAttribute("aria-invalid", "true");
    await expect(region).toHaveText("");
  });

  test("choices toggle and the select keeps native behaviour", async ({ page }) => {
    await page.getByRole("switch", { name: "Notifications" }).click();
    await expect(page.getByRole("switch", { name: "Notifications" })).toBeChecked();
    await page.getByRole("checkbox", { name: "Accept terms" }).click();
    await expect(page.getByRole("checkbox", { name: "Accept terms" })).toBeChecked();
    await page.getByRole("radio", { name: "Monthly" }).click();
    await expect(page.getByRole("radio", { name: "Monthly" })).toBeChecked();
    await page.getByLabel("Department").selectOption("finance");
    await expect(page.getByLabel("Department")).toHaveValue("finance");
  });

  test("loading, empty and error states are all present", async ({ page }) => {
    await expect(page.getByRole("status", { name: "Loading members" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "No members yet" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Invite member" })).toBeVisible();
    await expect(page.getByRole("alert").filter({ hasText: "Could not load usage" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  });

  test("passes axe, has no horizontal scroll and violates no CSP at every viewport", async ({ page, csp }) => {
    for (const viewport of Object.values(viewports)) {
      await page.setViewportSize(viewport);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
    expectNoCspViolations(csp);
  });
});