import { ADMIN_BACKEND, expect, installBackend, test } from "./support";

async function signIn(page: import("@playwright/test").Page, email: string, password = "correct-horse-battery") {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test.describe("login and per-company partition", () => {
  test("an admin of one organization lands on it without choosing", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await expect(page.getByRole("heading", { name: "Prometheon Forge" })).toBeVisible();
    await signIn(page, "admin@example.com");
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();
    await expect(page.getByRole("listitem").filter({ hasText: "Legal" })).toBeVisible();
    await expect(page.getByLabel("Organization")).toHaveCount(0);
    // The identity probe, the company branding and departments, and the dashboard's usage and roster reads; their order is concurrent.
    const org = "/forge/v1/orgs/11111111-1111-4111-8111-111111111111";
    expect(api.requests.map((r) => `${r.method} ${r.path}`).sort()).toEqual(
      [
        "POST /forge/v1/accounts/login",
        "GET /forge/v1/accounts/me",
        "GET /forge/v1/platform/me",
        `GET ${org}/branding`,
        `GET ${org}/departments`,
        `GET ${org}/members`,
        `GET ${org}/usage/members`,
        `GET ${org}/usage/members`,
      ].sort(),
    );
  });

  test("a plain member lands in the portal and no administration data is requested", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await signIn(page, "member@example.com");
    await expect(page.getByRole("heading", { level: 1, name: /Welcome/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Access denied" })).toHaveCount(0);
    expect(api.requests.filter((r) => /\/(members|departments|gateway|models|usage\/members)/.test(r.path))).toEqual([]);
  });

  test("wrong credentials show a generic error and clear the password", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await signIn(page, "admin@example.com", "wrong-password-value");
    await expect(page.getByRole("alert")).toHaveText("Email or password is incorrect.");
    await expect(page.getByLabel("Password")).toHaveValue("");
    await expect(page.getByLabel("Email")).toHaveValue("admin@example.com");
  });

  test("sign out returns to the login form and drops the session", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await signIn(page, "admin@example.com");
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    expect(api.requests.map((r) => `${r.method} ${r.path}`)).toContain("POST /forge/v1/accounts/logout");
    await expect(page.getByText("Org A")).toHaveCount(0);
  });
});

test.describe("organization scope", () => {
  test("only administered organizations are offered and none is preselected", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await signIn(page, "multi@example.com");
    const picker = page.getByLabel("Organization");
    await expect(picker.locator("option")).toHaveText(["Select an organization…", "Org A", "Org B"]);
    await expect(page.getByText("Select an organization to continue.")).toBeVisible();
    expect(api.requests.filter((r) => r.path.includes("/orgs/"))).toEqual([]);
  });

  test("switching organizations clears the previous data before the next loads", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await signIn(page, "multi@example.com");
    await page.getByLabel("Organization").selectOption({ label: "Org A" });
    await expect(page.getByRole("listitem").filter({ hasText: "Legal" })).toBeVisible();

    api.hold("22222222-2222-4222-8222-222222222222");
    await page.getByLabel("Organization").selectOption({ label: "Org B" });
    await expect(page.getByRole("status")).toHaveText("Loading departments…");
    await expect(page.getByText("Legal")).toHaveCount(0);
    api.letThrough("22222222-2222-4222-8222-222222222222");
    await expect(page.getByRole("listitem").filter({ hasText: "Finance" })).toBeVisible();
    await expect(page.getByText("Legal")).toHaveCount(0);
  });

  test("a late reply for the previous organization is never rendered", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await signIn(page, "multi@example.com");
    api.hold("11111111-1111-4111-8111-111111111111");
    await page.getByLabel("Organization").selectOption({ label: "Org A" });
    await page.getByLabel("Organization").selectOption({ label: "Org B" });
    await expect(page.getByRole("listitem").filter({ hasText: "Finance" })).toBeVisible();
    api.letThrough("11111111-1111-4111-8111-111111111111");
    await page.waitForResponse((r) => r.url().includes("/11111111-1111-4111-8111-111111111111/departments"));
    await expect(page.getByText("Legal")).toHaveCount(0);
    await expect(page.getByRole("listitem").filter({ hasText: "Finance" })).toBeVisible();
  });

  test("a stale organization id renders a generic not-found without data", async ({ page, adminUrl }) => {
    await installBackend(page, {
      ...ADMIN_BACKEND,
      departments: { ...ADMIN_BACKEND.departments, "11111111-1111-4111-8111-111111111111": { status: 404, items: [] } },
    });
    await page.goto(adminUrl);
    await signIn(page, "admin@example.com");
    await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
    await expect(page.getByText("The page you requested could not be found.")).toBeVisible();
    await expect(page.getByRole("main")).not.toContainText("11111111-1111-4111-8111-111111111111");
    await expect(page.getByText("Legal")).toHaveCount(0);
  });
});
