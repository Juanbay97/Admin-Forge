import type { Page } from "@playwright/test";
import { ADMIN_BACKEND, ORG_A, ORG_B, expect, installBackend, test } from "./support";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

async function openCatalog(page: Page, adminUrl: string, email = "admin@example.com") {
  await page.goto(adminUrl);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Sign in" }).click();
  if (email === "multi@example.com") await page.getByLabel("Organization").selectOption({ label: "Org A" });
  await page.getByRole("button", { name: "Catalog" }).click();
}

const published = (page: Page) => page.getByRole("list", { name: "Published aliases" }).getByRole("listitem");

test.describe("catalog status", () => {
  test("an unpublished organization shows no aliases", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openCatalog(page, adminUrl);
    await expect(page.getByRole("heading", { level: 1, name: "Catalog" })).toBeVisible();
    await expect(page.getByText("Not published")).toBeVisible();
    await expect(page.getByText("Catalog revision 0")).toBeVisible();
    await expect(page.getByText("No aliases are published.")).toBeVisible();
    expect(api.requests.some((r) => r.path.endsWith("/models"))).toBe(false);
  });

  test("a published organization lists exactly the aliases a member sees", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await openCatalog(page, adminUrl, "multi@example.com");
    await page.getByLabel("Organization").selectOption({ label: "Org B" });
    await expect(page.getByText("Published", { exact: true })).toBeVisible();
    await expect(page.getByText("Catalog revision 2")).toBeVisible();
    await expect(page.getByText("Default model: deep")).toBeVisible();
    await expect(published(page)).toHaveText(["deep", "quick"]);
  });

  test("a stale organization renders the generic not-found", async ({ page, adminUrl }) => {
    await installBackend(page, { ...ADMIN_BACKEND, catalogs: {} });
    await openCatalog(page, adminUrl);
    await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Refresh models" })).toHaveCount(0);
  });

  test("switching organizations clears the catalog before the next loads", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openCatalog(page, adminUrl, "multi@example.com");
    await page.getByRole("button", { name: "Refresh models" }).click();
    await expect(page.getByLabel("Alias for gpt-4o", { exact: true })).toBeVisible();
    api.hold(ORG_B);
    await page.getByLabel("Organization").selectOption({ label: "Org B" });
    await expect(page.getByRole("status")).toHaveText("Loading catalog…");
    await expect(page.getByLabel("Alias for gpt-4o", { exact: true })).toHaveCount(0);
    api.letThrough(ORG_B);
    await expect(published(page)).toHaveText(["deep", "quick"]);
    await expect(page.getByLabel("Alias for gpt-4o", { exact: true })).toHaveCount(0);
  });
});

test.describe("refresh and publish", () => {
  test("maps aliases to upstream ids and publishes with a default", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openCatalog(page, adminUrl);
    await page.getByRole("button", { name: "Refresh models" }).click();
    await expect(page.getByLabel("Alias for gpt-4o-mini", { exact: true })).toHaveValue("gpt-4o-mini");
    await expect(page.getByLabel("Alias for 4o-realtime", { exact: true })).toHaveValue("m-4o-realtime");

    await page.getByLabel("Publish 4o-realtime", { exact: true }).uncheck();
    await page.getByLabel("Alias for gpt-4o", { exact: true }).fill("smart");
    await page.getByLabel("Alias for gpt-4o-mini", { exact: true }).fill("fast");
    await page.getByLabel("Default: gpt-4o-mini", { exact: true }).check();
    await page.getByRole("button", { name: "Publish catalog" }).click();

    await expect(page.getByRole("status")).toHaveText("Published 2 aliases.");
    await expect(page.getByText("Catalog revision 1")).toBeVisible();
    await expect(page.getByText("Default model: fast")).toBeVisible();
    await expect(published(page)).toHaveText(["fast", "smart"]);
    const [body] = api.catalog(ORG_A)?.publications ?? [];
    expect(body).toMatchObject({
      expected_catalogue_revision: 0,
      expected_gateway_revision: 3,
      aliases: { smart: "gpt-4o", fast: "gpt-4o-mini" },
      default_alias: "fast",
    });
    expect((body as { operation_id: string }).operation_id).toMatch(UUID);
  });

  test("invalid selections are explained and nothing is sent", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openCatalog(page, adminUrl);
    await page.getByRole("button", { name: "Refresh models" }).click();
    await page.getByLabel("Alias for gpt-4o", { exact: true }).fill("Bad Alias");
    await page.getByLabel("Alias for gpt-4o-mini", { exact: true }).fill("same");
    await page.getByLabel("Alias for 4o-realtime", { exact: true }).fill("same");
    await page.getByRole("button", { name: "Publish catalog" }).click();
    const problems = page.getByRole("alert").getByRole("listitem");
    await expect(problems).toHaveText([
      'Alias "Bad Alias" must start with a letter and use only lowercase letters, digits, "-" and "_".',
      'Alias "same" is used more than once.',
    ]);
    expect(api.catalog(ORG_A)?.publications).toEqual([]);
  });

  test("a changed gateway shows a conflict and publishes nothing", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openCatalog(page, adminUrl);
    await page.getByRole("button", { name: "Refresh models" }).click();
    await expect(page.getByLabel("Alias for gpt-4o", { exact: true })).toBeVisible();
    api.bumpCatalog(ORG_A);
    await page.getByRole("button", { name: "Publish catalog" }).click();
    await expect(page.getByRole("alert")).toHaveText(
      "The catalog or gateway changed since the models were refreshed. Refresh the models and try again.",
    );
    await expect(page.getByText("Not published")).toBeVisible();
    expect(api.catalog(ORG_A)?.aliases).toEqual({});

    await page.getByRole("button", { name: "Refresh models" }).click();
    await page.getByRole("button", { name: "Publish catalog" }).click();
    await expect(page.getByRole("status")).toHaveText("Published 3 aliases.");
    expect(api.catalog(ORG_A)?.revision).toBe(1);
  });

  test("refresh lists only the models inside the platform ceiling", async ({ page, adminUrl }) => {
    const ceilinged = { ...ADMIN_BACKEND.catalogs?.[ORG_A], ceiling: ["gpt-4o-mini"] } as NonNullable<typeof ADMIN_BACKEND.catalogs>[string];
    await installBackend(page, { ...ADMIN_BACKEND, catalogs: { [ORG_A]: ceilinged } });
    await openCatalog(page, adminUrl);
    await page.getByRole("button", { name: "Refresh models" }).click();
    await expect(page.getByLabel("Alias for gpt-4o-mini", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Alias for gpt-4o", { exact: true })).toHaveCount(0);
    await expect(page.getByLabel("Alias for 4o-realtime", { exact: true })).toHaveCount(0);
  });

  test("a publication outside a ceiling the platform just narrowed says the ceiling is the reason", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openCatalog(page, adminUrl);
    await page.getByRole("button", { name: "Refresh models" }).click();
    await expect(page.getByLabel("Alias for gpt-4o", { exact: true })).toBeVisible();
    api.setCeiling(ORG_A, ["gpt-4o-mini"]);
    await page.getByRole("button", { name: "Publish catalog" }).click();
    await expect(page.getByRole("alert")).toHaveText(
      "One or more selected models are not allowed by the platform for this company. Refresh the models and choose from the allowed ones.",
    );
    await expect(page.getByText("Not published")).toBeVisible();
    expect(api.catalog(ORG_A)?.aliases).toEqual({});
  });

  test("an unreachable gateway is reported without detail", async ({ page, adminUrl }) => {
    const unreachable = { ...ADMIN_BACKEND.catalogs?.[ORG_A], upstream: null } as NonNullable<typeof ADMIN_BACKEND.catalogs>[string];
    await installBackend(page, { ...ADMIN_BACKEND, catalogs: { [ORG_A]: unreachable } });
    await openCatalog(page, adminUrl);
    await page.getByRole("button", { name: "Refresh models" }).click();
    await expect(page.getByRole("alert")).toHaveText(
      "The gateway could not be reached. Check the gateway settings, then try again.",
    );
    await expect(page.getByRole("button", { name: "Publish catalog" })).toHaveCount(0);
  });
});

test.describe("accessibility", () => {
  test("the mapping is operable with the keyboard alone", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openCatalog(page, adminUrl);
    const refresh = page.getByRole("button", { name: "Refresh models" });
    await refresh.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByLabel("Alias for gpt-4o", { exact: true })).toBeVisible();
    await page.getByLabel("Publish gpt-4o", { exact: true }).focus();
    await page.keyboard.press("Space"); // unchecks the first row
    await page.keyboard.press("Tab"); // the dropped row's alias and default controls are disabled
    await expect(page.getByLabel("Publish gpt-4o-mini", { exact: true })).toBeFocused();
    await page.getByRole("button", { name: "Publish catalog" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("status")).toHaveText("Published 2 aliases.");
    expect(api.catalog(ORG_A)?.defaultModel).toBe("gpt-4o-mini");
  });

  test("honors prefers-reduced-motion", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await openCatalog(page, adminUrl);
    const duration = () =>
      page.getByRole("button", { name: "Refresh models" }).evaluate((el) => getComputedStyle(el).transitionDuration);
    expect(await duration()).not.toBe("0s");
    await page.emulateMedia({ reducedMotion: "reduce" });
    expect(await duration()).toBe("0s");
  });
});
