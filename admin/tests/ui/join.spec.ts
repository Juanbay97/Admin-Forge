import type { Page } from "@playwright/test";
import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { CAPABILITY, INVITATION, MEMBER, PASSWORD, installPortal, newPortalWorld, type PortalWorld } from "./portalSupport";

const LINK = (code = "acme", capability = CAPABILITY) => `join?c=${code}#invitation_id=${INVITATION}&capability=${capability}`;

async function open(page: Page, adminUrl: string, link: string, world: PortalWorld = newPortalWorld()) {
  const backend = await installPortal(page, world);
  await page.goto(adminUrl + link);
  return backend;
}
async function fill(page: Page, { email = MEMBER.email, password = PASSWORD, confirm = password }: { email?: string; password?: string; confirm?: string } = {}) {
  await page.getByLabel("Your email").fill(email);
  await page.getByLabel("New password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(confirm);
}
const submit = (page: Page) => page.getByRole("button", { name: "Create password and continue" });

test.describe("join page", () => {
  test("is branded for the company code before the form shows, calls nothing authenticated and scrubs the link", async ({ page, adminUrl, context }) => {
    const { requests } = await open(page, adminUrl, LINK());
    await expect(page.getByRole("heading", { name: "Create your password" })).toBeVisible();
    await expect(page.getByText("Acme Forge")).toBeVisible();
    await expect(page.getByText("Welcome to Acme. Let us get you set up.")).toBeVisible();
    await expect(page).toHaveTitle(/Acme Forge/);
    const variables = await page.evaluate(() => [...document.documentElement.style].filter((name) => name.startsWith("--brand-")).map((name) => document.documentElement.style.getPropertyValue(name)).join(" ").toLowerCase());
    expect(variables).toMatch(/#1d4ed8|#b45309|#eff6ff/); // the company's palette is applied, not the Prometheon default
    expect(new URL(page.url()).hash).toBe("");
    expect(page.url()).not.toContain(CAPABILITY);
    expect(requests.filter((request) => request.authorization !== null || /accounts\/me|platform/.test(request.path))).toEqual([]);
    expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain(CAPABILITY);
    expect(await context.cookies()).toEqual([]);
  });

  test("an unknown company code is the Prometheon look, not an error", async ({ page, adminUrl }) => {
    await open(page, adminUrl, LINK("nobody"));
    await expect(page.getByRole("heading", { name: "Create your password" })).toBeVisible();
    await expect(page.getByText("Prometheon Forge").first()).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("a slow branding lookup never blocks the page for more than a moment, then re-themes", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.brandingDelayMs = 1800;
    await open(page, adminUrl, LINK(), world);
    await expect(page.getByRole("heading", { name: "Create your password" })).toBeVisible({ timeout: 1600 });
    await expect(page.getByText("Prometheon Forge").first()).toBeVisible();
    await expect(page.getByText("Acme Forge")).toBeVisible({ timeout: 4000 });
  });

  test("success: the account is accepted once, signed in and sent to the download page", async ({ page, adminUrl }) => {
    const { requests, world } = await open(page, adminUrl, LINK());
    await fill(page);
    await submit(page).click();
    await expect(page).toHaveURL(/\/admin\/portal\/download/);
    const accepts = requests.filter((request) => request.path.endsWith("/invitations/accept"));
    expect(accepts).toHaveLength(1);
    expect(accepts[0]?.body).toEqual({ invitation_id: INVITATION, capability: CAPABILITY, password: PASSWORD });
    expect(world.accepted).toBe(1);
    const login = requests.find((request) => request.path.endsWith("/accounts/login"));
    expect(login?.body).toEqual({ email: MEMBER.email, password: PASSWORD });
  });

  test("when the server names the invited person the email is not asked for and the sign-in uses it", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.preview = { [CAPABILITY]: { account_email: MEMBER.email, display_name: MEMBER.name } };
    const { requests } = await open(page, adminUrl, LINK(), world);
    await expect(page.getByRole("heading", { name: "Create your password" })).toBeVisible();
    await expect(page.getByText(MEMBER.email)).toBeVisible();
    await expect(page.getByLabel("Your email")).toHaveCount(0);
    await page.getByLabel("New password", { exact: true }).fill(PASSWORD);
    await page.getByLabel("Confirm password").fill(PASSWORD);
    await submit(page).click();
    await expect(page).toHaveURL(/\/admin\/portal\/download/);
    expect(requests.find((request) => request.path.endsWith("/accounts/login"))?.body).toEqual({ email: MEMBER.email, password: PASSWORD });
    expect(requests.find((request) => request.path.endsWith("/invitations/accept"))?.body).toEqual({ invitation_id: INVITATION, capability: CAPABILITY, password: PASSWORD });
    expect(requests.filter((request) => request.authorization !== null)).toEqual([]);
  });

  test("an unusable invitation is explained before anything is typed, in words that do not say which case it is", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.preview = {}; // the server's uniform 404: expired, used, withdrawn, wrong or unknown are indistinguishable
    const { requests } = await open(page, adminUrl, LINK(), world);
    await expect(page.getByRole("heading", { name: "This invitation can no longer be used" })).toBeVisible();
    await expect(page.getByText(/expired.*used.*withdrawn|expired, been used/i)).toBeVisible();
    await expect(page.getByLabel("New password", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
    await expect(page.getByText(/NOT_FOUND|INVITATION_|404/)).toHaveCount(0);
    expect(requests.filter((request) => request.path.endsWith("/invitations/accept"))).toEqual([]);
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });

  test("a preview outage keeps the form and asks for the email as before", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.preview = "outage";
    await open(page, adminUrl, LINK(), world);
    await expect(page.getByRole("heading", { name: "Create your password" })).toBeVisible();
    await fill(page);
    await submit(page).click();
    await expect(page).toHaveURL(/portal\/download/);
  });

  test("a double click submits once", async ({ page, adminUrl }) => {
    const { world } = await open(page, adminUrl, LINK());
    await fill(page);
    await submit(page).dblclick();
    await expect(page).toHaveURL(/portal\/download/);
    expect(world.accepted).toBe(1);
  });

  test("the password is checked before anything is sent, and the form stays editable on a policy refusal", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl, LINK());
    await fill(page, { password: "short", confirm: "short" });
    await submit(page).click();
    await expect(page.getByText("Use at least 15 characters.")).toBeVisible();
    await fill(page, { confirm: "different-password-123" });
    await submit(page).click();
    await expect(page.getByText("The passwords do not match.")).toBeVisible();
    expect(requests.filter((request) => request.path.endsWith("/accept"))).toEqual([]);
  });

  test("an email that is not an address is asked for again", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl, LINK());
    await fill(page, { email: "not-an-email" });
    await submit(page).click();
    await expect(page.getByText("Enter the email address this invitation was sent to.")).toBeVisible();
    expect(requests.filter((request) => request.path.endsWith("/accept"))).toEqual([]);
  });

  for (const [name, kind, heading] of [
    ["an expired, used or unknown invitation", "invalid", "This invitation can no longer be used"],
    ["an existing account", "existing", "You already have a Forge account"],
  ] as const) {
    test(`${name} gets its own state with the next step and no technical code`, async ({ page, adminUrl }) => {
      const world = newPortalWorld();
      world.invitations[CAPABILITY] = kind;
      await open(page, adminUrl, LINK(), world);
      await fill(page);
      await submit(page).click();
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
      await expect(page.getByText(/NOT_FOUND|EXISTING_ACCOUNT|INVITATION_/)).toHaveCount(0);
      await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
    });
  }

  test("an outage or being offline keeps the form so the person can retry", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.invitations[CAPABILITY] = "outage";
    await open(page, adminUrl, LINK(), world);
    await fill(page);
    await submit(page).click();
    await expect(page.getByRole("alert")).toContainText("unavailable");
    world.invitations[CAPABILITY] = "valid";
    await fill(page);
    await submit(page).click();
    await expect(page).toHaveURL(/portal\/download/);
  });

  test("a link without its fragment is explained", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "join?c=acme");
    await expect(page.getByRole("heading", { name: "This invitation link is incomplete" })).toBeVisible();
    await expect(page.getByLabel("New password", { exact: true })).toHaveCount(0);
  });

  test("a signed-in visitor is not auto-accepted", async ({ page, adminUrl }) => {
    const { requests, world } = await open(page, adminUrl, LINK());
    await fill(page);
    await submit(page).click();
    await expect(page).toHaveURL(/portal\/download/);
    await page.evaluate((hash) => {
      history.pushState(null, "", `/admin/join?c=acme${hash}`);
      window.dispatchEvent(new PopStateEvent("popstate"));
    }, `#invitation_id=${INVITATION}&capability=${CAPABILITY}`);
    await expect(page.getByRole("heading", { name: "You are already signed in" })).toBeVisible();
    expect(world.accepted).toBe(1);
    expect(requests.filter((request) => request.path.endsWith("/accept"))).toHaveLength(1);
  });

  test("is accessible, readable on a phone and fits every viewport", async ({ page, adminUrl }) => {
    await open(page, adminUrl, LINK());
    await expect(page.getByRole("heading", { name: "Create your password" })).toBeVisible();
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
    await page.setViewportSize(viewports.mobile);
    const box = await submit(page).boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  });
});