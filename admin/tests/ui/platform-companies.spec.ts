import type { Page } from "@playwright/test";
import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { ACME, GLOBEX, OWNER, installPlatform, newWorld } from "./platformSupport";

async function open(page: Page, adminUrl: string, path: string, world = newWorld()) {
  world.mfa.verified = true;
  const backend = await installPlatform(page, world);
  await page.goto(adminUrl + path);
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Password").fill(OWNER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  return backend;
}

test.describe("company list", () => {
  test("lists companies with status and 30-day usage; the row leads to the detail", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "platform/companies");
    await expect(page.getByRole("heading", { level: 1, name: "Companies" })).toBeVisible();
    const table = page.getByRole("table", { name: "Companies" });
    const acme = table.getByRole("row", { name: /Acme Corp/ });
    await expect(acme.getByText("acme", { exact: true })).toBeVisible();
    await expect(acme.getByText("Active")).toBeVisible();
    await expect(acme.getByText("1.4K")).toBeVisible();
    await expect(table.getByRole("row", { name: /Globex/ }).getByText("Suspended")).toBeVisible();
    await table.getByRole("link", { name: "Acme Corp" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Acme Corp" })).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/platform/companies/${ACME}`));
  });

  test("search and status filter are in the URL and survive a reload", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "platform/companies");
    await page.getByLabel("Search companies").fill("glob");
    await expect(page).toHaveURL(/q=glob/);
    await expect(page.getByRole("table", { name: "Companies" }).getByRole("row")).toHaveCount(2); // header + Globex
    await page.getByLabel("Search companies").fill("");
    await page.getByLabel("Status").selectOption("suspended");
    await expect(page).toHaveURL(/status=suspended/);
    await page.reload();
    await page.getByLabel("Email").fill(OWNER.email);
    await page.getByLabel("Password").fill(OWNER.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByLabel("Status")).toHaveValue("suspended");
    const table = page.getByRole("table", { name: "Companies" });
    await expect(table.getByRole("link", { name: "Globex" })).toBeVisible();
    await expect(table.getByRole("link", { name: "Acme Corp" })).toHaveCount(0);
  });

  test("no match and no companies are different, helpful states", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "platform/companies?q=zzz");
    await expect(page.getByText("No companies match")).toBeVisible();
  });

  test("an empty platform offers the wizard", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.companies = [];
    await open(page, adminUrl, "platform/companies", world);
    await expect(page.getByRole("heading", { name: "No companies yet" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Create company" }).first()).toHaveAttribute("href", "/admin/platform/companies/new");
  });

  test("is accessible in light and dark on every viewport", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "platform/companies");
    await expect(page.getByRole("table", { name: "Companies" })).toBeVisible();
    for (const dark of [false, true]) {
      if (dark) await page.getByRole("button", { name: "Switch to dark mode" }).click();
      for (const size of Object.values(viewports)) {
        await page.setViewportSize(size);
        await expectNoHorizontalScroll(page);
        await expectAccessible(page);
      }
    }
  });
});

test.describe("company detail", () => {
  test("shows the status, code and the setup checklist, and Finish setup while keys or models are missing", async ({ page, adminUrl }) => {
    await open(page, adminUrl, `platform/companies/${GLOBEX}`);
    await expect(page.getByRole("heading", { level: 1, name: "Globex" })).toBeVisible();
    await expect(page.getByText("Code: globex")).toBeVisible();
    await expect(page.getByRole("region", { name: "Setup" }).getByText("Gateway keys")).toBeVisible();
    await expect(page.getByText("Finish setup")).toBeVisible();
  });

  test("a complete company has no setup banner", async ({ page, adminUrl }) => {
    await open(page, adminUrl, `platform/companies/${ACME}`);
    await expect(page.getByRole("heading", { level: 1, name: "Acme Corp" })).toBeVisible();
    await expect(page.getByText("Finish setup")).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Setup" }).getByText("Models")).toBeVisible();
  });

  test("suspending needs the exact company code, shows the effect, and the company reads as suspended", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl, `platform/companies/${ACME}`);
    await page.getByRole("button", { name: "Suspend company" }).click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog.getByText("Members lose access immediately")).toBeVisible();
    const confirm = dialog.getByRole("button", { name: "Suspend" });
    await expect(confirm).toBeDisabled();
    await dialog.getByLabel("Type acme to confirm").fill("acm");
    await expect(confirm).toBeDisabled();
    await dialog.getByLabel("Type acme to confirm").fill("acme");
    await confirm.click();
    await expect(page.getByText("This company is suspended")).toBeVisible();
    await expect(page.getByText("Acme Corp suspended")).toBeVisible(); // the toast
    expect(requests.filter((request) => request.path.endsWith(`/${ACME}/suspend`))).toHaveLength(1);
    await page.getByRole("button", { name: "Reactivate company" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Reactivate" }).click();
    await expect(page.getByText("This company is suspended")).toHaveCount(0);
  });

  test("an unknown company is a plain not-found", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "platform/companies/00000000-0000-4000-8000-000000000000");
    await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
  });

  test("is accessible in light and dark on every viewport", async ({ page, adminUrl }) => {
    await open(page, adminUrl, `platform/companies/${GLOBEX}`);
    await expect(page.getByRole("heading", { level: 1, name: "Globex" })).toBeVisible();
    for (const dark of [false, true]) {
      if (dark) await page.getByRole("button", { name: "Switch to dark mode" }).click();
      for (const size of Object.values(viewports)) {
        await page.setViewportSize(size);
        await expectNoHorizontalScroll(page);
        await expectAccessible(page);
      }
    }
  });
});