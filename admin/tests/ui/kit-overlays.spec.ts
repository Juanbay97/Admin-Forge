import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";

test.describe("kit overlays and data gallery", () => {
  test.beforeEach(async ({ page, origin }) => {
    await page.goto(`${origin}/admin/?kit=overlays`);
    await expect(page.getByRole("heading", { level: 1, name: "Kit overlays and data" })).toBeVisible();
  });

  test("a dialog traps focus, closes with Escape and returns focus to its trigger", async ({ page }) => {
    const trigger = page.getByRole("button", { name: "Open dialog" });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "Rename workspace" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel("Workspace name")).toBeFocused();
    for (let press = 0; press < 6; press++) {
      await page.keyboard.press("Tab");
      // Focus stays in the dialog or leaves the page for the browser chrome (the native modal behaviour); it never reaches the inert page.
      expect(await dialog.evaluate((element) => element.contains(document.activeElement) || document.activeElement === document.body)).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("clicking the backdrop closes a dialog and the close button does too", async ({ page }) => {
    await page.getByRole("button", { name: "Open dialog" }).click();
    const dialog = page.getByRole("dialog", { name: "Rename workspace" });
    await page.mouse.click(5, 5);
    await expect(dialog).toBeHidden();
    await page.getByRole("button", { name: "Open dialog" }).click();
    await dialog.getByRole("button", { name: "Close" }).click();
    await expect(dialog).toBeHidden();
  });

  test("an alert dialog starts on the safe choice, cancels with Escape and confirms on request", async ({ page }) => {
    await page.getByRole("button", { name: "Delete workspace" }).click();
    const alert = page.getByRole("alertdialog", { name: "Delete workspace?" });
    await expect(alert).toBeVisible();
    await expect(alert.getByRole("button", { name: "Cancel" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(alert).toBeHidden();
    await expect(page.getByText("Deleted: no")).toBeVisible();
    await page.getByRole("button", { name: "Delete workspace" }).click();
    await alert.getByRole("button", { name: "Delete" }).click();
    await expect(alert).toBeHidden();
    await expect(page.getByText("Deleted: yes")).toBeVisible();
  });

  test("a sheet slides in from the side and is a modal dialog", async ({ page }) => {
    await page.getByRole("button", { name: "Open sheet" }).click();
    const sheet = page.getByRole("dialog", { name: "Filters" });
    await expect(sheet).toBeVisible();
    const box = await sheet.boundingBox();
    expect(box!.x + box!.width).toBeGreaterThanOrEqual(page.viewportSize()!.width - 1);
    expect(box!.height).toBeGreaterThanOrEqual(page.viewportSize()!.height - 1);
    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();
  });

  test("toasts appear in a polite live region and can be dismissed", async ({ page }) => {
    const region = page.getByRole("region", { name: "Notifications" });
    await expect(region).toHaveAttribute("aria-live", "polite");
    await page.getByRole("button", { name: "Show toast" }).click();
    await expect(region.getByText("Catalogue published")).toBeVisible();
    await region.getByRole("button", { name: "Dismiss Catalogue published" }).click();
    await expect(region.getByText("Catalogue published")).toHaveCount(0);
  });

  test("tabs move with the arrow keys; tooltip and non-modal menu work from the keyboard", async ({ page }) => {
    await page.getByRole("tab", { name: "Overview" }).focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "Usage" })).toHaveAttribute("aria-selected", "true");
    await page.getByRole("button", { name: "Copy help" }).focus();
    await expect(page.getByRole("tooltip")).toContainText("Copies the value");
    const trigger = page.getByRole("button", { name: "Row actions" });
    await trigger.click();
    await expect(page.getByRole("menuitem", { name: "Rename" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
  });

  test("the data table sorts, filters and paginates", async ({ page }) => {
    const table = page.getByRole("table", { name: "People" });
    const names = () => table.locator("tbody tr td:first-child").allInnerTexts();
    expect(await names()).toEqual(["Alex", "Bea", "Cy", "Dee", "Eli"]);
    await table.getByRole("button", { name: "Tokens" }).click();
    await expect(table.getByRole("columnheader", { name: "Tokens" })).toHaveAttribute("aria-sort", "ascending");
    expect((await names())[0]).toBe("Lou");
    await table.getByRole("button", { name: "Tokens" }).click();
    await expect(table.getByRole("columnheader", { name: "Tokens" })).toHaveAttribute("aria-sort", "descending");
    expect((await names())[0]).toBe("Kim");
    await page.getByRole("navigation", { name: "Pagination" }).getByRole("button", { name: "Next" }).click();
    await expect(page.getByText("Page 2 of 3")).toBeVisible();
    await page.getByLabel("Filter people").fill("bea");
    expect(await names()).toEqual(["Bea"]);
    await expect(page.getByText("Page 1 of 1")).toBeVisible();
    await page.getByLabel("Filter people").fill("zzz");
    await expect(page.getByRole("heading", { name: "Nobody matches" })).toBeVisible();
  });

  test("a loading table shows skeleton rows, not an empty table", async ({ page }) => {
    const loading = page.getByRole("status", { name: "Loading people" });
    await expect(loading).toBeVisible();
    await expect(loading.getByRole("table")).toHaveCount(0);
  });

  test("copy confirms and a key field never reveals or keeps the secret", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.getByRole("button", { name: "Copy invite link" }).click();
    await expect(page.getByRole("button", { name: "Copied" })).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("https://forge.example/join/abc");

    const key = page.getByLabel("API key");
    await expect(key).toHaveAttribute("type", "password");
    await expect(key).toHaveAttribute("autocomplete", "off");
    await expect(page.getByText("Saved key ending in 4f2a")).toBeVisible();
    await key.fill("sk-live-secret");
    await page.getByRole("button", { name: "Save key" }).click();
    await expect(key).toHaveValue("");
    await expect(page.getByText("Submitted 14 characters")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.outerHTML.includes("sk-live-secret"))).toBe(false);
  });

  test("passes axe and fits every viewport with an overlay open", async ({ page }) => {
    for (const viewport of Object.values(viewports)) {
      await page.setViewportSize(viewport);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
    await page.getByRole("button", { name: "Open dialog" }).click();
    await expectAccessible(page);
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Delete workspace" }).click();
    await expectAccessible(page);
  });
});