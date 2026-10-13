import type { Page } from "@playwright/test";
import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { OWNER, installPlatform, newWorld } from "./platformSupport";

async function open(page: Page, adminUrl: string, world = newWorld()) {
  world.mfa.verified = true;
  const backend = await installPlatform(page, world);
  await page.goto(adminUrl + "platform/companies/new");
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Password").fill(OWNER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Create a company" })).toBeVisible();
  return backend;
}

const next = (page: Page) => page.getByRole("button", { name: "Next" });

async function company(page: Page, name = "Initech", code?: string) {
  await page.getByLabel("Company name").fill(name);
  if (code) await page.getByLabel("Company code").fill(code);
  await next(page).click();
}
async function brandingDefault(page: Page) {
  await expect(page.getByRole("heading", { name: "Branding" })).toBeVisible();
  await next(page).click();
}
async function admin(page: Page) {
  await page.getByLabel("Administrator email").fill("ada@initech.test");
  await page.getByLabel("Administrator name").fill("Ada Lovelace");
  await next(page).click();
}
async function keysAndModels(page: Page) {
  await page.getByRole("checkbox", { name: /Primary/ }).check();
  await page.getByLabel("Add a model").fill("gpt-4o");
  await page.getByRole("button", { name: "Add model" }).click();
  await next(page).click();
}

test.describe("create-company wizard", () => {
  test("happy path: five steps, review, create, success with the code and the invitation", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl);
    const stepper = page.getByRole("list", { name: "Steps" });
    await expect(stepper.locator("[aria-current=step]")).toHaveText(/Company/);
    await page.getByLabel("Company name").fill("Initech Corp");
    await expect(page.getByLabel("Company code")).toHaveValue("initech-corp"); // suggested from the name
    await page.getByLabel("Company code").fill("initech");
    await expect(page.getByText("Code is available")).toBeVisible();
    await next(page).click();
    await expect(stepper.locator("[aria-current=step]")).toHaveText(/Branding/);
    await brandingDefault(page);
    await admin(page);
    await keysAndModels(page);
    await expect(page.getByRole("heading", { name: "Review and create" })).toBeVisible();
    const review = page.getByRole("region", { name: "Summary" });
    await expect(review.getByText("Initech Corp")).toBeVisible();
    await expect(review.getByText("initech", { exact: true })).toBeVisible();
    await expect(review.getByText("ada@initech.test")).toBeVisible();
    await expect(review.getByText("Default Prometheon look")).toBeVisible();
    await expect(review.getByText("gpt-4o")).toBeVisible();
    await page.getByRole("button", { name: "Create company" }).click();
    await expect(page.getByRole("heading", { name: "Initech Corp is ready" })).toBeVisible();
    await expect(page.getByText("Invitation sent to ada@initech.test")).toBeVisible();
    await expect(page.getByText("initech", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Open company" })).toHaveAttribute("href", /\/admin\/platform\/companies\/99999999/);
    const writes = requests.filter((request) => request.method !== "GET" && request.path.includes("/companies")).map((request) => `${request.method} ${request.path.replace(/99999999-9999-4999-8999-\d+/, "{id}").replace("/forge/v1/platform", "")}`);
    expect(writes).toEqual(["POST /companies", "PUT /companies/{id}/gateway-keys", "PUT /companies/{id}/model-access"]);
  });

  test("the stepper and the form data survive going back", async ({ page, adminUrl }) => {
    await open(page, adminUrl);
    await company(page, "Initech");
    await brandingDefault(page);
    await page.getByLabel("Administrator email").fill("ada@initech.test");
    await page.getByRole("button", { name: "Back" }).click();
    await page.getByRole("button", { name: "Back" }).click();
    await expect(page.getByLabel("Company name")).toHaveValue("Initech");
    await next(page).click();
    await next(page).click();
    await expect(page.getByLabel("Administrator email")).toHaveValue(""); // an unsaved step is not remembered, a saved one is
  });

  test("a code already in use is refused in step 1 and Next stays disabled", async ({ page, adminUrl }) => {
    await open(page, adminUrl);
    await page.getByLabel("Company name").fill("Acme");
    await expect(page.getByText("Code is taken")).toBeVisible();
    await expect(next(page)).toBeDisabled();
    await page.getByLabel("Company code").fill("acme-two");
    await expect(page.getByText("Code is available")).toBeVisible();
    await expect(next(page)).toBeEnabled();
  });

  test("a failed step is named, retried alone, and the company page shows Finish setup until it is fixed", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.failOnce["PUT /companies/"] = { status: 503, code: "SERVICE_UNAVAILABLE", times: 1 }; // the key assignment fails once; the saga does not retry on its own
    const { requests } = await open(page, adminUrl, world);
    await company(page);
    await brandingDefault(page);
    await admin(page);
    await keysAndModels(page);
    await page.getByRole("button", { name: "Create company" }).click();
    const progress = page.getByRole("list", { name: "Setup steps" });
    await expect(progress.getByRole("listitem").filter({ hasText: "Company" })).toContainText("Done");
    await expect(progress.getByRole("listitem").filter({ hasText: "Gateway keys" })).toContainText("Failed");
    await expect(progress.getByRole("listitem").filter({ hasText: "Models" })).toContainText("Waiting");
    await expect(page.getByRole("alert")).toContainText("The company exists");
    await page.getByRole("button", { name: "Retry failed steps" }).click();
    await expect(page.getByRole("heading", { name: "Initech is ready" })).toBeVisible();
    expect(requests.filter((request) => request.method === "POST" && request.path.endsWith("/companies"))).toHaveLength(1);
  });

  test("a failed invitation delivery is reported without calling the company a failure", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.delivery = "failed";
    await open(page, adminUrl, world);
    await company(page);
    await brandingDefault(page);
    await admin(page);
    await keysAndModels(page);
    await page.getByRole("button", { name: "Create company" }).click();
    await expect(page.getByRole("heading", { name: "Initech is ready" })).toBeVisible();
    await expect(page.getByText("The invitation email could not be sent")).toBeVisible();
  });

  test("custom branding is validated live and applied after the company exists", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl);
    await company(page);
    await page.getByRole("checkbox", { name: "Customize branding" }).check();
    await page.getByLabel("Primary color", { exact: true }).fill("#FFFF00");
    await expect(page.getByTestId("issue-primary")).toBeVisible();
    await expect(next(page)).toBeDisabled();
    await page.getByLabel("Primary color", { exact: true }).fill("#123456");
    await expect(next(page)).toBeEnabled();
    await expect(page.getByLabel("Logos")).toHaveCount(0); // the platform API has no logo upload
    await next(page).click();
    await admin(page);
    await keysAndModels(page);
    await page.getByRole("button", { name: "Create company" }).click();
    await expect(page.getByRole("heading", { name: "Initech is ready" })).toBeVisible();
    expect(requests.some((request) => request.method === "PUT" && request.path.endsWith("/branding"))).toBe(true);
    expect(await page.evaluate(() => document.documentElement.style.getPropertyValue("--brand-primary"))).not.toBe("#123456"); // the console never wears a company theme
  });

  test("is accessible and fits every viewport on the steps", async ({ page, adminUrl }) => {
    await open(page, adminUrl);
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
    await company(page);
    await expect(page.getByRole("heading", { name: "Branding" })).toBeVisible();
    await page.getByRole("checkbox", { name: "Customize branding" }).check();
    await page.setViewportSize(viewports.mobile);
    await expectNoHorizontalScroll(page);
    await expectAccessible(page, { exclude: ['[aria-label$="preview"]'] }); // the previews illustrate a company theme, not this console
  });

  test("works with the keyboard alone", async ({ page, adminUrl }) => {
    await open(page, adminUrl);
    await page.getByLabel("Company name").focus();
    await page.keyboard.type("Keyboard Co");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Branding" })).toBeVisible();
    await page.keyboard.press("Tab"); // skips nothing it should not
    await expect(page.locator(":focus")).toBeVisible();
  });
});