import type { Page } from "@playwright/test";
import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { ACME, GLOBEX, OWNER, installPlatform, newWorld } from "./platformSupport";

async function open(page: Page, adminUrl: string, path: string, state = newWorld()) {
  state.mfa.verified = true;
  const backend = await installPlatform(page, state);
  await page.goto(adminUrl + path);
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Password").fill(OWNER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  return backend;
}

const MODELS = `platform/companies/${ACME}?tab=models`;
const catalogCalls = (requests: Array<{ method: string; path: string }>) => requests.filter((request) => request.path.includes("/catalog"));

test.describe("platform catalog: discover, select, alias, default and publish", () => {
  test("the owner discovers models, searches, selects two with aliases and a default, and publishes once", async ({ page, adminUrl }) => {
    const { requests, world } = await open(page, adminUrl, MODELS);
    await expect(page.getByText("Not published")).toBeVisible();
    await expect(page.getByText("Last discovered: never")).toBeVisible();
    await expect(page.getByText("No models discovered yet")).toBeVisible();

    await page.getByRole("button", { name: "Discover models" }).click();
    const keys = page.getByRole("list", { name: "Key discovery" });
    await expect(keys.getByRole("listitem").filter({ hasText: "primary" })).toContainText("Reachable");
    await expect(keys.getByRole("listitem").filter({ hasText: "primary" })).toContainText("4 models");
    await expect(keys.getByRole("listitem").filter({ hasText: "backup" })).toContainText("Not reachable");
    await expect(page.getByText("Last discovered: Oct 14, 2026, 12:00 UTC")).toBeVisible();
    const list = page.getByRole("list", { name: "Discovered models" });
    await expect(list.getByRole("listitem")).toHaveCount(4);
    await expect(page.getByText("0 of 4 selected")).toBeVisible();

    await page.getByLabel("Search models").fill("GPT");
    await expect(list.getByRole("listitem")).toHaveCount(2);
    await expect(page.getByText("0 of 4 selected · 2 shown")).toBeVisible();
    await page.getByLabel("Select gpt-4o-mini").check();
    await page.getByLabel("Alias for gpt-4o-mini").fill("fast");
    await page.getByLabel("Search models").fill("combo");
    await page.getByLabel("Select combo/fast").check();
    await page.getByLabel("Alias for combo/fast").fill("smart");
    await page.getByLabel("Default model combo/fast").check();
    await page.getByLabel("Search models").fill("");
    await expect(page.getByText("2 of 4 selected")).toBeVisible();

    await page.getByRole("button", { name: "Publish catalog" }).click();
    await expect(page.getByText("Catalog published")).toBeVisible();
    const puts = requests.filter((request) => request.method === "PUT" && request.path.endsWith("/catalog"));
    expect(puts).toHaveLength(1);
    expect(puts[0]?.body).toEqual({ expected_catalogue_revision: 0, expected_gateway_revision: 1, aliases: { fast: "gpt-4o-mini", smart: "combo/fast" }, default_alias: "smart" });
    await expect(page.getByText("Published", { exact: true })).toBeVisible();
    await expect(page.getByText("Catalog revision 1")).toBeVisible();
    // The published selection comes back preselected, and the allowed models follow it.
    await expect(page.getByLabel("Select gpt-4o-mini")).toBeChecked();
    await expect(page.getByLabel("Alias for combo/fast")).toHaveValue("smart");
    await expect(page.getByLabel("Default model combo/fast")).toBeChecked();
    await expect(page.getByRole("table", { name: "Allowed models" }).getByRole("row", { name: /combo\/fast/ })).toBeVisible();
    expect(world.models[ACME]).toEqual(["combo/fast", "gpt-4o-mini"]);
  });

  test("select shown and clear shown act on the search result only", async ({ page, adminUrl }) => {
    await open(page, adminUrl, MODELS);
    await page.getByRole("button", { name: "Discover models" }).click();
    await page.getByLabel("Search models").fill("gpt");
    await page.getByRole("button", { name: "Select shown" }).click();
    await expect(page.getByText("2 of 4 selected · 2 shown")).toBeVisible();
    await page.getByLabel("Search models").fill("nothing-matches");
    await expect(page.getByText('No model matches "nothing-matches".')).toBeVisible();
    await page.getByLabel("Search models").fill("");
    await page.getByRole("button", { name: "Clear shown" }).click();
    await expect(page.getByText("0 of 4 selected")).toBeVisible();
  });

  test("a selection that cannot be published is explained before anything is sent", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl, MODELS);
    await page.getByRole("button", { name: "Discover models" }).click();
    await page.getByRole("button", { name: "Publish catalog" }).click();
    await expect(page.getByRole("alert")).toContainText("Select at least one model.");
    await page.getByLabel("Select gpt-4o", { exact: true }).check();
    await page.getByLabel("Select gpt-4o-mini").check();
    await page.getByLabel("Alias for gpt-4o-mini").fill("gpt-4o");
    await page.getByRole("button", { name: "Publish catalog" }).click();
    await expect(page.getByRole("alert")).toContainText('Alias "gpt-4o" is used more than once.');
    await page.getByLabel("Alias for gpt-4o-mini").fill("Bad Alias");
    await page.getByRole("button", { name: "Publish catalog" }).click();
    await expect(page.getByRole("alert")).toContainText("must start with a letter");
    expect(requests.filter((request) => request.method === "PUT" && request.path.endsWith("/catalog"))).toEqual([]);
  });

  test("a key that fails is reported by name and state, never with the server's words", async ({ page, adminUrl }) => {
    const state = newWorld();
    state.discoveries[ACME] = {
      model_ids: [],
      keys: [
        { key_id: "77777777-7777-4777-8777-000000000001", label: "primary", origin: "https://gateway.example.test", priority: 1, state: "unreachable", model_count: 0, model_ids: [] },
        { key_id: "77777777-7777-4777-8777-000000000002", label: "spare", origin: "https://gateway.example.test", priority: 2, state: "no_key", model_count: 0, model_ids: [] },
        { key_id: "77777777-7777-4777-8777-000000000003", label: "retired", origin: "https://gateway.example.test", priority: 3, state: "disabled", model_count: 0, model_ids: [] },
      ],
    };
    await open(page, adminUrl, MODELS, state);
    await page.getByRole("button", { name: "Discover models" }).click();
    const keys = page.getByRole("list", { name: "Key discovery" });
    await expect(keys.getByRole("listitem").filter({ hasText: "primary" })).toContainText("Not reachable");
    await expect(keys.getByRole("listitem").filter({ hasText: "spare" })).toContainText("No key stored");
    await expect(keys.getByRole("listitem").filter({ hasText: "retired" })).toContainText("Disabled");
    await expect(page.getByText("No key answered, so nothing was stored.")).toBeVisible();
    await expect(page.getByText("Last discovered: never")).toBeVisible();
  });

  test("a failed discovery says so and keeps what was there", async ({ page, adminUrl }) => {
    const state = newWorld();
    state.catalogs[ACME]!.discovered = { ids: ["gpt-4o"], at: "2026-10-01T08:30:00+00:00" };
    state.failOnce["POST /companies/" + ACME + "/catalog/discover"] = { status: 503, code: "SERVICE_UNAVAILABLE" };
    await open(page, adminUrl, MODELS, state);
    await expect(page.getByText("Last discovered: Oct 1, 2026, 08:30 UTC")).toBeVisible();
    await page.getByRole("button", { name: "Discover models" }).click();
    await expect(page.getByRole("alert")).toContainText("Discovery could not be completed");
    await expect(page.getByLabel("Select gpt-4o")).toBeVisible();
  });

  test("a publish that raced another change asks for a new discovery and the page is not stale", async ({ page, adminUrl }) => {
    const { world } = await open(page, adminUrl, MODELS);
    await page.getByRole("button", { name: "Discover models" }).click();
    await page.getByLabel("Select gpt-4o", { exact: true }).check();
    world.catalogs[ACME]!.revision = 3; // another owner session published meanwhile
    await page.getByRole("button", { name: "Publish catalog" }).click();
    await expect(page.getByRole("alert")).toContainText("Discover the models again");
    await expect(page.getByLabel("Select gpt-4o", { exact: true })).toBeChecked();
  });

  test("a company with no gateway key assigned has nothing to discover yet", async ({ page, adminUrl }) => {
    const state = newWorld();
    delete state.catalogs[ACME];
    const { requests } = await open(page, adminUrl, MODELS, state);
    await expect(page.getByText("No gateway key assigned")).toBeVisible();
    await expect(page.getByRole("button", { name: "Discover models" })).toHaveCount(0);
    expect(catalogCalls(requests).map((request) => request.method)).toEqual(["GET"]);
  });

  test("a suspended company's catalog is shown read-only", async ({ page, adminUrl }) => {
    const state = newWorld();
    state.catalogs[GLOBEX] = { gatewayRevision: 1, discovered: { ids: ["gpt-4o", "gpt-4o-mini"], at: "2026-10-01T08:30:00+00:00" }, revision: 2, defaultAlias: "main", aliases: { main: "gpt-4o" } };
    await open(page, adminUrl, `platform/companies/${GLOBEX}?tab=models`, state);
    await expect(page.getByText("Reactivate the company to change its catalog.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Discover models" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Publish catalog" })).toHaveCount(0);
    await expect(page.getByLabel("Select gpt-4o", { exact: true })).toBeDisabled();
    await expect(page.getByLabel("Alias for gpt-4o", { exact: true })).toHaveValue("main");
  });

  test("is accessible and fits every viewport, discovered or not", async ({ page, adminUrl }) => {
    await open(page, adminUrl, MODELS);
    await page.getByRole("button", { name: "Discover models" }).click();
    await page.getByLabel("Select gpt-4o", { exact: true }).check();
    await expect(page.getByRole("list", { name: "Discovered models" })).toBeVisible();
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});
