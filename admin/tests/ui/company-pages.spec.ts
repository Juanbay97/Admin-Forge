import type { Page } from "@playwright/test";
import { ADMIN_BACKEND, ORG_A, expect, expectAccessible, expectNoHorizontalScroll, installBackend, test, viewports, type Backend } from "./support";

async function signIn(page: Page, email = "admin@example.com", password = "correct-horse-battery") {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

const nav = (page: Page, name: string) => page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name });
const row = (page: Page, name: string) => page.getByRole("row").filter({ hasText: name });

async function everyViewport(page: Page, check: () => Promise<void>) {
  for (const viewport of Object.values(viewports)) {
    await page.setViewportSize(viewport);
    await expectNoHorizontalScroll(page);
    await check();
  }
}

test.describe("sign-in", () => {
  test("an empty submit shows each field's error, marks the inputs invalid and sends nothing", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("Enter your email address.")).toBeVisible();
    await expect(page.getByText("Enter your password.")).toBeVisible();
    await expect(page.getByLabel("Email")).toHaveAttribute("aria-invalid", "true");
    await expect(page.getByLabel("Password")).toHaveAttribute("aria-invalid", "true");
    expect(api.requests).toEqual([]);
  });

  test("a malformed email is explained and fixing it clears the error", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await page.getByLabel("Email").fill("not-an-email");
    await page.getByLabel("Password").fill("x");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("Enter a valid email address.")).toBeVisible();
    await page.getByLabel("Email").fill("admin@example.com");
    await expect(page.getByText("Enter a valid email address.")).toHaveCount(0);
  });

  test("a refused sign-in keeps the email, clears the password and is announced once", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await signIn(page, "admin@example.com", "wrong-password-value");
    await expect(page.getByRole("alert")).toHaveText("Email or password is incorrect.");
    await expect(page.getByLabel("Password")).toHaveValue("");
    await expect(page.getByLabel("Email")).toHaveValue("admin@example.com");
    await expect(page.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });

  test("is accessible and fits every viewport, with and without an error", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await everyViewport(page, () => expectAccessible(page));
    await signIn(page, "admin@example.com", "wrong-password-value");
    await expect(page.getByRole("alert")).toBeVisible();
    await everyViewport(page, () => expectAccessible(page));
  });
});

test.describe("overview", () => {
  test("shows a skeleton while departments load, then the summary and the list", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    api.hold(ORG_A);
    await page.goto(adminUrl);
    await signIn(page);
    await expect(page.getByRole("status")).toHaveText("Loading departments…");
    api.letThrough(ORG_A);
    await expect(page.getByRole("listitem").filter({ hasText: "Legal" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Summary" })).toContainText("Departments");
    await expect(page.getByRole("region", { name: "Summary" })).toContainText("1");
    await expect(page.getByRole("region", { name: "Summary" })).toContainText("Administrator");
  });

  test("an organization without departments gets an empty state, not an empty list", async ({ page, adminUrl }) => {
    await installBackend(page, { ...ADMIN_BACKEND, departments: { ...ADMIN_BACKEND.departments, [ORG_A]: { status: 200, items: [] } } });
    await page.goto(adminUrl);
    await signIn(page);
    await expect(page.getByRole("heading", { name: "No departments yet" })).toBeVisible();
    await expect(page.getByRole("list").filter({ hasText: "Legal" })).toHaveCount(0);
  });

  test("a failed load is an alert with a retry that recovers", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    let failures = 1;
    await page.route("**/departments", (route) => (failures-- > 0 ? route.fulfill({ status: 500, body: "" }) : route.fallback()));
    await page.goto(adminUrl);
    await signIn(page);
    await expect(page.getByRole("alert")).toContainText("Something went wrong. Try again.");
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByRole("listitem").filter({ hasText: "Legal" })).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("is accessible at every viewport", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await signIn(page);
    await expect(page.getByRole("listitem").filter({ hasText: "Legal" })).toBeVisible();
    await everyViewport(page, () => expectAccessible(page));
  });
});

test.describe("members", () => {
  const open = async (page: Page, adminUrl: string, backend: Backend = ADMIN_BACKEND) => {
    const api = await installBackend(page, backend);
    await page.goto(adminUrl);
    await signIn(page);
    await nav(page, "Members").click();
    return api;
  };

  test("an organization with no members gets an empty state whose action opens the invitation", async ({ page, adminUrl }) => {
    await open(page, adminUrl, { ...ADMIN_BACKEND, members: { ...ADMIN_BACKEND.members, [ORG_A]: [] } });
    await expect(page.getByRole("heading", { name: "No members yet" })).toBeVisible();
    await page.getByRole("button", { name: "Invite your first member" }).click();
    await expect(page.getByRole("dialog", { name: "Invite a member" })).toBeVisible();
  });

  test("shows skeleton rows while loading", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await signIn(page);
    await expect(page.getByRole("listitem").filter({ hasText: "Legal" })).toBeVisible();
    api.hold(ORG_A);
    await nav(page, "Members").click();
    await expect(page.getByRole("status")).toHaveText("Loading members…");
    await expect(page.getByRole("table")).toHaveCount(0);
    api.letThrough(ORG_A);
    await expect(row(page, "Pat Member")).toBeVisible();
  });

  test("suspending asks for confirmation: Cancel changes nothing, Suspend does", async ({ page, adminUrl }) => {
    const api = await open(page, adminUrl);
    await page.getByRole("button", { name: "Suspend Pat Member" }).click();
    const confirm = page.getByRole("alertdialog", { name: "Suspend Pat Member?" });
    await expect(confirm).toBeVisible();
    await expect(confirm.getByRole("button", { name: "Cancel" })).toBeFocused();
    await confirm.getByRole("button", { name: "Cancel" }).click();
    await expect(row(page, "Pat Member")).toContainText("Active");
    expect(api.requests.filter((request) => request.path.endsWith("/suspend"))).toEqual([]);
    await page.getByRole("button", { name: "Suspend Pat Member" }).click();
    await confirm.getByRole("button", { name: "Suspend" }).click();
    await expect(row(page, "Pat Member")).toContainText("Suspended");
    expect(api.requests.filter((request) => request.path.endsWith("/suspend"))).toHaveLength(1);
  });

  test("the list can be searched and sorted", async ({ page, adminUrl }) => {
    await open(page, adminUrl);
    const names = () => page.getByRole("table").locator("tbody tr td:first-child .font-medium").allInnerTexts();
    await expect.poll(names).toEqual(["Alex Admin", "Pat Member"]);
    await page.getByRole("table").getByRole("button", { name: "Name" }).click();
    await page.getByRole("table").getByRole("button", { name: "Name" }).click();
    await expect.poll(names).toEqual(["Pat Member", "Alex Admin"]);
    await page.getByLabel("Search members").fill("alex@");
    await expect.poll(names).toEqual(["Alex Admin"]);
    await page.getByLabel("Search members").fill("nobody");
    await expect(page.getByRole("heading", { name: "No members match" })).toBeVisible();
  });

  test("is accessible at every viewport, with the invitation dialog and the confirmation open", async ({ page, adminUrl }) => {
    await open(page, adminUrl);
    await expect(row(page, "Pat Member")).toBeVisible();
    await everyViewport(page, () => expectAccessible(page));
    await page.setViewportSize(viewports.desktop);
    await page.getByRole("button", { name: "Invite member" }).click();
    await expectAccessible(page);
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Suspend Pat Member" }).click();
    await expectAccessible(page);
  });
});