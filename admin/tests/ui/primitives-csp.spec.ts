// Slice-1 spike: every allow-listed third-party primitive is mounted in the production test bundle and driven.
// The global CSP fixture fails the test if any of them creates a <style> element or otherwise breaks `style-src 'self'`.
import { expect, test } from "./support";
import { expectNoCspViolations } from "./quality";

test.describe("allow-listed primitives under the production CSP", () => {
  test.beforeEach(async ({ page, origin }) => {
    await page.goto(`${origin}/admin/?kit=primitives`);
    await expect(page.getByRole("heading", { level: 1, name: "Primitive spike" })).toBeVisible();
  });

  test("Tabs switch panels", async ({ page }) => {
    await page.getByRole("tab", { name: "Usage" }).click();
    await expect(page.getByRole("tabpanel", { name: "Usage" })).toBeVisible();
  });

  test("Tooltip opens on focus and Popover on click", async ({ page }) => {
    await page.getByRole("button", { name: "Tooltip trigger" }).focus();
    await expect(page.getByRole("tooltip")).toHaveText(/Copies the value/);
    await page.getByRole("button", { name: "Popover trigger" }).click();
    await expect(page.getByText("Popover body")).toBeVisible();
  });

  test("non-modal DropdownMenu opens, moves with the keyboard and closes with Escape", async ({ page }) => {
    const trigger = page.getByRole("button", { name: "Menu trigger" });
    await trigger.click();
    await expect(page.getByRole("menuitem", { name: "Rename" })).toBeVisible();
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("menuitem", { name: "Rename" })).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });

  test("Switch, Checkbox and RadioGroup change state", async ({ page }) => {
    await page.getByRole("switch", { name: "Notifications" }).click();
    await expect(page.getByRole("switch", { name: "Notifications" })).toBeChecked();
    await page.getByRole("checkbox", { name: "Accept terms" }).click();
    await expect(page.getByRole("checkbox", { name: "Accept terms" })).toBeChecked();
    await page.getByRole("radio", { name: "Monthly" }).click();
    await expect(page.getByRole("radio", { name: "Monthly" })).toBeChecked();
    await expect(page.getByRole("radio", { name: "Weekly" })).not.toBeChecked();
  });

  test("Slot renders a link with the button styling hook and cmdk filters its list", async ({ page }) => {
    await expect(page.getByRole("link", { name: "Slot link" })).toHaveAttribute("href", "#slot");
    await page.getByPlaceholder("Search commands").fill("mem");
    await expect(page.getByRole("option", { name: "Members" })).toBeVisible();
    await expect(page.getByRole("option", { name: "Gateway" })).toHaveCount(0);
  });

  test("a lucide icon renders as inline SVG", async ({ page }) => {
    await expect(page.locator("svg.lucide")).toHaveCount(1);
  });

  test("nothing in the spike violated the CSP", async ({ csp }) => {
    expectNoCspViolations(csp);
  });
});