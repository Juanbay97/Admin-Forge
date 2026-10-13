import type { Page } from "@playwright/test";
import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { OWNER, installPlatform, newWorld } from "./platformSupport";

async function open(page: Page, adminUrl: string, path: string) {
  const world = newWorld();
  world.mfa.verified = true;
  const backend = await installPlatform(page, world);
  await page.goto(adminUrl + path);
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Password").fill(OWNER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  return backend;
}

const SECRET = "sk-live-9f8e7d6c5b4a3210WXYZ";

test.describe("gateway key pool", () => {
  test("lists keys by label, gateway, last four and use, never more of the secret", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "platform/keys");
    const table = page.getByRole("table", { name: "Gateway keys" });
    const row = table.getByRole("row", { name: /Primary/ });
    await expect(row.getByText("gateway.example.test")).toBeVisible();
    await expect(row.getByText("••••a1b2")).toBeVisible();
    await expect(row.getByText("Active", { exact: true })).toBeVisible();
    await expect(row.getByText("2", { exact: true })).toBeVisible();
  });

  test("adding a key sends it once, empties the field and shows only the last four", async ({ page, adminUrl }) => {
    const { requests, world } = await open(page, adminUrl, "platform/keys");
    await page.getByRole("button", { name: "Add key" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Label").fill("Backup");
    await dialog.getByLabel("Gateway").selectOption("https://gateway.example.test");
    const field = dialog.getByLabel("API key");
    await expect(field).toHaveAttribute("type", "password");
    await field.fill(SECRET);
    await dialog.getByRole("button", { name: "Add key" }).click();
    await expect(page.getByRole("table", { name: "Gateway keys" }).getByRole("row", { name: /Backup/ }).getByText("••••WXYZ")).toBeVisible();
    expect(requests.filter((request) => request.method === "POST" && request.path.endsWith("/gateway-keys"))).toHaveLength(1);
    expect(world.secrets).toEqual([SECRET]);
    expect(await page.content()).not.toContain(SECRET);
    expect(await page.content()).not.toContain("sk-live-9f8e");
    expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain("sk-live");
    await page.getByRole("button", { name: "Add key" }).click();
    await expect(page.getByRole("dialog").getByLabel("API key")).toHaveValue("");
  });

  test("a duplicate label is refused inside the dialog and the secret field is emptied", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "platform/keys");
    await page.getByRole("button", { name: "Add key" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Label").fill("Primary");
    await dialog.getByLabel("API key").fill(SECRET);
    await dialog.getByRole("button", { name: "Add key" }).click();
    await expect(dialog.getByRole("alert")).toContainText("already exists");
    await expect(dialog.getByLabel("API key")).toHaveValue("");
  });

  test("rotating replaces the key text and disabling asks first, naming the companies that use it", async ({ page, adminUrl }) => {
    const { world } = await open(page, adminUrl, "platform/keys");
    const row = page.getByRole("table", { name: "Gateway keys" }).getByRole("row", { name: /Primary/ });
    await row.getByRole("button", { name: "Rotate Primary" }).click();
    await page.getByRole("dialog").getByLabel("New API key").fill(SECRET);
    await page.getByRole("dialog").getByRole("button", { name: "Rotate key" }).click();
    await expect(row.getByText("••••WXYZ")).toBeVisible();
    expect(world.secrets).toContain(SECRET);
    await row.getByRole("button", { name: "Disable Primary" }).click();
    const confirm = page.getByRole("alertdialog");
    await expect(confirm).toContainText("2 companies");
    await confirm.getByRole("button", { name: "Disable key" }).click();
    await expect(row.getByText("Disabled")).toBeVisible();
    await row.getByRole("button", { name: "Enable Primary" }).click();
    await expect(row.getByText("Active", { exact: true })).toBeVisible();
  });

  test("an empty pool explains what to do", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.keys = [];
    world.mfa.verified = true;
    await installPlatform(page, world);
    await page.goto(adminUrl + "platform/keys");
    await page.getByLabel("Email").fill(OWNER.email);
    await page.getByLabel("Password").fill(OWNER.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "No gateway keys yet" })).toBeVisible();
  });

  test("is accessible on every viewport, light and dark, with the dialog open", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "platform/keys");
    await expect(page.getByRole("table", { name: "Gateway keys" })).toBeVisible();
    for (const dark of [false, true]) {
      if (dark) await page.getByRole("button", { name: "Switch to dark mode" }).click();
      for (const size of Object.values(viewports)) {
        await page.setViewportSize(size);
        await expectNoHorizontalScroll(page);
        await expectAccessible(page);
      }
    }
    await page.getByRole("button", { name: "Add key" }).click();
    await expectAccessible(page);
  });
});

test.describe("model prices", () => {
  test("lists the newest price of each model in USD per million tokens", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "platform/prices");
    const row = page.getByRole("table", { name: "Model prices" }).getByRole("row", { name: /gpt-4o/ });
    await expect(row.getByText("$2.50")).toBeVisible();
    await expect(row.getByText("$10.00")).toBeVisible();
    await expect(row.getByText("v2")).toBeVisible();
  });

  test("editing converts USD to micro-USD integers and appends a version", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl, "platform/prices");
    await page.getByRole("button", { name: "Add price" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Model").fill("claude-3-5-sonnet");
    await dialog.getByLabel("Input, USD per 1M tokens").fill("3.00");
    await dialog.getByLabel("Output, USD per 1M tokens").fill("15.00");
    await dialog.getByRole("button", { name: "Save price" }).click();
    await expect(page.getByRole("table", { name: "Model prices" }).getByRole("row", { name: /claude-3-5-sonnet/ }).getByText("$15.00")).toBeVisible();
    const post = requests.find((request) => request.method === "POST" && request.path.endsWith("/prices"));
    expect(post?.body).toEqual({ upstream_id: "claude-3-5-sonnet", input_micros: 3_000_000, output_micros: 15_000_000 });
  });

  test("invalid amounts and past dates are explained and nothing is sent", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl, "platform/prices");
    const row = page.getByRole("table", { name: "Model prices" }).getByRole("row", { name: /gpt-4o/ });
    await row.getByRole("button", { name: "Edit gpt-4o" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByLabel("Model")).toHaveValue("gpt-4o");
    await dialog.getByLabel("Input, USD per 1M tokens").fill("-1");
    await dialog.getByLabel("Output, USD per 1M tokens").fill("1.0000001");
    await dialog.getByLabel("Effective from").fill("2020-01-01");
    await dialog.getByRole("button", { name: "Save price" }).click();
    await expect(dialog.getByText(/non-negative amount/).first()).toBeVisible();
    await expect(dialog.getByText("The date cannot be in the past.")).toBeVisible();
    expect(requests.filter((request) => request.method === "POST" && request.path.endsWith("/prices"))).toEqual([]);
  });

  test("the history drawer lists every version of a model", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "platform/prices");
    await page.getByRole("button", { name: "History gpt-4o" }).click();
    const drawer = page.getByRole("dialog", { name: /Price history/ });
    await expect(drawer.getByRole("row", { name: /v2/ })).toBeVisible();
  });

  test("is accessible on every viewport", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "platform/prices");
    await expect(page.getByRole("table", { name: "Model prices" })).toBeVisible();
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});