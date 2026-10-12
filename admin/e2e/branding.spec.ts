import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { makePng } from "../tests/png";

// Real stack (owned PostgreSQL, two seeded organizations, control plane serving the production bundle),
// started by scripts\admin-e2e.ps1. Nothing here is mocked: validation, CAS, the sanitizer and the
// public endpoint are the server's own.
interface Credentials {
  organizations: Array<{
    slug: string;
    organization_id: string;
    accounts: Array<{ email: string; role: string; password: string }>;
  }>;
}

const file = process.env.FORGE_E2E_CREDENTIALS;
if (!file) throw new Error("FORGE_E2E_CREDENTIALS is not set: run scripts\\admin-e2e.ps1.");
const credentials = JSON.parse(readFileSync(file, "utf-8")) as Credentials;

function seeded(slug: string) {
  const organization = credentials.organizations.find((item) => item.slug === slug);
  const admin = organization?.accounts.find((account) => account.role === "organization_admin");
  if (!organization || !admin) throw new Error(`The seeded ${slug} administrator is missing from the credentials file.`);
  return { id: organization.organization_id, slug, admin };
}

const orgA = seeded("org-a");
const orgB = seeded("org-b");
const ASSET_URL = /^\/forge\/v1\/branding\/assets\/([0-9a-f]{64})$/;

// The local stack seeds org-a as Northwind Logistics (revision 1, blue, with an isotipo) and org-b as Lumen Finance
// (revision 1, purple). The test brands org-a again with golden vector "near-black primary"
// (contract/branding-palette.vectors.json) so the change is visible against the seed.
const SEEDED_A = { name: "Northwind Logistics", primary: "#1D4ED8", title: "Northwind Logistics Admin" };
const SEEDED_B = { name: "Lumen Finance", primary: "#7C3AED", title: "Lumen Finance Admin" };
const ACME = {
  name: "Acme Labs",
  loginCopy: "Sign in to the Acme workspace.",
  primary: "#101820",
  accent: "#B91C1C",
  tint: "#F3F4F6",
  lightBrand: "rgb(16, 24, 32)",
  darkBrand: "rgb(124, 128, 132)",
  ink: "#05070A",
};

interface PublicBranding {
  revision: number;
  name: string;
  loginCopy: string;
  theme: Record<string, string>;
  assets: Record<string, string>;
}

const field = (page: Page, name: string) => page.getByLabel(name, { exact: true });
const rootVar = (page: Page, name: string) => page.evaluate((n) => document.documentElement.style.getPropertyValue(n), name);

async function signIn(page: Page, account: { email: string; password: string }) {
  await page.goto("/admin/");
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function token(request: APIRequestContext, account: { email: string; password: string }) {
  const login = await request.post("/forge/v1/accounts/login", { data: { email: account.email, password: account.password } });
  expect(login.ok()).toBe(true);
  return ((await login.json()) as { access_token: string }).access_token;
}

/** The control plane keeps at most 8 live sessions per account and this suite shares the stack with others: leave none behind. */
async function revoke(request: APIRequestContext, headers: { Authorization: string }) {
  expect((await request.post("/forge/v1/accounts/logout", { headers })).status()).toBe(204);
}

async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
}

async function publicBranding(request: APIRequestContext, slug: string) {
  const response = await request.get(`/forge/v1/branding?org=${slug}`);
  expect(response.status()).toBe(200);
  return (await response.json()) as PublicBranding;
}

/** Records real CSP violations (browser events) for the whole page life. */
async function watchViolations(page: Page) {
  await page.addInitScript(() => {
    (window as unknown as { __csp: string[] }).__csp = [];
    document.addEventListener("securitypolicyviolation", (event) =>
      (window as unknown as { __csp: string[] }).__csp.push(`${event.violatedDirective} ${event.blockedURI}`),
    );
  });
  return () => page.evaluate(() => (window as unknown as { __csp: string[] }).__csp);
}

test("an admin brands org-a with colors, name and a logo; org-b is unaffected; reset restores the default", async ({ page, browser, request }) => {
  const violations = await watchViolations(page);
  const logo = makePng(120, 60, [30, 90, 200]);

  await test.step("both organizations start on their own seeded branding, each with its isotipo", async () => {
    for (const [slug, seeded] of [["org-a", SEEDED_A], ["org-b", SEEDED_B]] as const) {
      const view = await publicBranding(request, slug);
      expect(view).toMatchObject({ revision: 1, name: seeded.name, theme: { primary: seeded.primary } });
      expect(Object.keys(view.assets)).toEqual(["isotipo"]);
    }
  });

  await test.step("edit the branding and see the live preview while the chrome stays put", async () => {
    await signIn(page, orgA.admin);
    await expect(page.getByRole("heading", { level: 1, name: "Organization A" })).toBeVisible();
    await page.getByRole("button", { name: "Branding" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Branding" })).toBeVisible();
    await expect(field(page, "Product name")).toHaveValue(SEEDED_A.name);
    // The real control plane tells the administrator which code employees type: the seeded slug.
    const companyCode = page.getByRole("group", { name: "Company code" });
    await expect(companyCode.getByTestId("company-code")).toHaveText(orgA.slug);
    await expect(companyCode).toContainText("Employees type this code the first time they open the app");
    await expect(companyCode.getByRole("button", { name: "Copy company code" })).toBeVisible();

    await field(page, "Product name").fill(ACME.name);
    await field(page, "Login message").fill(ACME.loginCopy);
    await field(page, "Primary color").fill(ACME.primary);
    await field(page, "Accent color").fill(ACME.accent);
    await field(page, "Background tint").fill(ACME.tint);
    await field(page, "Heading font").selectOption("nunito-sans");
    await field(page, "Body font").selectOption("ibm-plex-sans");
    await field(page, "Logo for light backgrounds").setInputFiles({ name: "acme.png", mimeType: "image/png", buffer: logo });
    await expect(page.getByText("Uploaded 120×60 px. It goes live when you save.")).toBeVisible();

    const preview = (mode: string) => page.getByRole("group", { name: `${mode} preview` });
    await expect(preview("Light").getByTestId("preview-button")).toHaveCSS("background-color", ACME.lightBrand);
    await expect(preview("Dark").getByTestId("preview-button")).toHaveCSS("background-color", ACME.darkBrand);
    await expect(preview("Light")).toContainText(ACME.name);
    await expect(preview("Light").locator("canvas")).toBeVisible();
    // The client sign-in screen and the browser tab follow the draft too.
    await expect(preview("Light").getByRole("heading", { name: `Welcome to ${ACME.name}` })).toBeVisible();
    await expect(preview("Light")).toContainText(ACME.loginCopy);
    await expect(page.getByRole("group", { name: "Browser tab preview" })).toContainText(ACME.name);
    // Nothing is saved yet: the shell, the title and the public endpoint still show the seeded branding.
    expect(await rootVar(page, "--brand-teal")).toBe(SEEDED_A.primary);
    expect(await page.title()).toBe(SEEDED_A.title);
    expect((await publicBranding(request, "org-a")).name).toBe(SEEDED_A.name);
  });

  let logoUrl = "";
  await test.step("save publishes revision 2 and re-themes the shell", async () => {
    await page.getByRole("button", { name: "Save branding" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Branding saved" })).toHaveText("Branding saved (revision 2).");
    expect(await rootVar(page, "--brand-teal")).toBe(ACME.primary);
    expect(await rootVar(page, "--brand-primary")).toBe(ACME.ink);
    await expect(page.locator("header")).toContainText(ACME.name);
    expect(await page.title()).toBe("Acme Labs Admin");
    await expect(page.getByTestId("company-code")).toHaveText(orgA.slug);
    logoUrl = (await publicBranding(request, "org-a")).assets.logoLight ?? "";
    expect(logoUrl).toMatch(ASSET_URL);
    await expect(page.locator("header img")).toHaveAttribute("src", logoUrl);
  });

  await test.step("a reload (a new sign-in) shows the saved branding, fonts and logo", async () => {
    await page.reload();
    await page.getByLabel("Email").fill(orgA.admin.email);
    await page.getByLabel("Password").fill(orgA.admin.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.locator("header")).toContainText(ACME.name);
    expect(await page.title()).toBe("Acme Labs Admin");
    expect(await rootVar(page, "--brand-teal")).toBe(ACME.primary);
    await expect
      .poll(() => page.locator("header img").evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth))
      .toBe(120);
    await expect
      .poll(() =>
        page.evaluate(async () => {
          await document.fonts.ready;
          return [...document.fonts].some((face) => face.family.includes("Nunito Sans") && face.status === "loaded");
        }),
      )
      .toBe(true);
    await page.getByRole("button", { name: "Branding" }).click();
    await expect(field(page, "Product name")).toHaveValue(ACME.name);
    await expect(field(page, "Primary color")).toHaveValue(ACME.primary);
    await expect(field(page, "Heading font")).toHaveValue("nunito-sans");
    await expect(page.getByText("The current logo is published.").first()).toBeVisible();
  });

  await test.step("the public endpoint and the content-addressed asset serve exactly what was saved", async () => {
    const view = await publicBranding(request, "org-a");
    expect(view).toMatchObject({
      revision: 2,
      name: ACME.name,
      loginCopy: ACME.loginCopy,
      theme: { primary: ACME.primary, accent: ACME.accent, tint: ACME.tint, heading: "nunito-sans", body: "ibm-plex-sans" },
    });
    // The seeded isotipo is kept by the form; the new light logo is added next to it.
    expect(Object.keys(view.assets).sort()).toEqual(["isotipo", "logoLight"]);
    const asset = await request.get(logoUrl);
    expect(asset.status()).toBe(200);
    expect(asset.headers()["content-type"]).toBe("image/png");
    expect(asset.headers()["x-content-type-options"]).toBe("nosniff");
    expect(asset.headers()["cache-control"]).toContain("immutable");
    const sha = ASSET_URL.exec(logoUrl)?.[1];
    expect(createHash("sha256").update(await asset.body()).digest("hex")).toBe(sha);
  });

  await test.step("org-b is untouched, publicly and for its own administrator", async () => {
    expect(await publicBranding(request, "org-b")).toMatchObject({ revision: 1, name: SEEDED_B.name });
    const other = await browser.newContext({ baseURL: process.env.FORGE_E2E_ADMIN_URL });
    try {
      const second = await other.newPage();
      await signIn(second, orgB.admin);
      await expect(second.getByRole("heading", { level: 1, name: "Organization B" })).toBeVisible();
      await expect(second.locator("header")).toContainText(SEEDED_B.name);
      await expect(second.locator("header")).not.toContainText(ACME.name);
      expect(await rootVar(second, "--brand-teal")).toBe(SEEDED_B.primary);
      expect(await second.title()).toBe(SEEDED_B.title);
      await signOut(second);
    } finally {
      await other.close();
    }
    // The org-a administrator cannot read or write org-b's branding.
    const bearer = { Authorization: `Bearer ${await token(request, orgA.admin)}` };
    const crossRead = await request.get(`/forge/v1/orgs/${orgB.id}/branding`, { headers: bearer });
    expect(crossRead.status()).toBe(404);
    const crossWrite = await request.post(`/forge/v1/orgs/${orgB.id}/branding/reset`, { headers: bearer, data: { expectedRevision: 1 } });
    expect(crossWrite.status()).toBe(404);
    expect((await publicBranding(request, "org-b")).revision).toBe(1);
    await revoke(request, bearer);
  });

  await test.step("reset restores the Prometheon default as a new revision", async () => {
    await page.getByRole("button", { name: "Reset to default" }).click();
    await expect(page.getByText("Reset to the Prometheon default?")).toBeVisible();
    await page.getByRole("button", { name: "Confirm reset" }).click();
    await expect(page.getByRole("status").filter({ hasText: "reset" })).toHaveText("Branding reset to the Prometheon default (revision 3).");
    await expect(field(page, "Product name")).toHaveValue("Prometheon Forge");
    await expect(field(page, "Primary color")).toHaveValue("#0B1D26");
    expect(await rootVar(page, "--brand-teal")).toBe("#0F6B6D");
    expect(await rootVar(page, "--brand-primary")).toBe("#0B1D26");
    expect(await page.title()).toBe("Prometheon Forge Admin");
    await expect(page.locator("header")).toContainText("Prometheon Forge");
    const view = await publicBranding(request, "org-a");
    expect(view).toMatchObject({ revision: 3, name: "Prometheon Forge" });
    expect(view.assets).toEqual({});
    // The superseded logo is no longer referenced by a current revision, so it is no longer served.
    expect((await request.get(logoUrl)).status()).toBe(404);
  });

  await signOut(page);
  expect(await violations()).toEqual([]);
});

test("hostile inputs are refused with the server's own message and nothing is saved", async ({ page, request }) => {
  const violations = await watchViolations(page);
  const before = await publicBranding(request, "org-a");
  await signIn(page, orgA.admin);
  await page.getByRole("button", { name: "Branding" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Branding" })).toBeVisible();

  async function refused(label: string, value: string, message: string) {
    await field(page, label).fill(value);
    await page.getByRole("button", { name: "Save branding" }).click();
    await expect(page.getByRole("alert")).toHaveText(message);
    await field(page, label).fill(label === "Product name" ? before.name : before.theme.primary ?? "#0B1D26");
  }

  await test.step("text and color fields", async () => {
    await refused("Product name", "}</style><script>alert(1)</script>", "The product name must be 1 to 40 plain characters.");
    await refused("Product name", "Evil\u202EName", "The product name must be 1 to 40 plain characters.");
    await refused("Product name", "x".repeat(41), "The product name must be 1 to 40 plain characters.");
    await refused("Primary color", "red; } body{display:none", "A color must be a #RRGGBB hex value.");
    await refused("Primary color", "#FFFF00", "The primary color must reach 3:1 contrast against white.");
  });

  await test.step("a color the apps cannot render readably never leaves the page", async () => {
    await field(page, "Accent color").fill("#FFEB3B");
    await expect(page.getByTestId("preview-unavailable")).toBeVisible();
    // Flagged live by the shared generator, before Save; the server then gives its own refusal.
    await expect(page.getByTestId("issue-accent")).toContainText("3:1");
    await page.getByRole("button", { name: "Save branding" }).click();
    await expect(page.getByRole("alert")).toContainText("cannot produce a readable theme");
    await field(page, "Accent color").fill(before.theme.accent ?? "#E07A2D");
  });

  await test.step("uploads: SVG, oversize, malformed and out-of-range images", async () => {
    const uploads: Array<[string, { name: string; mimeType: string; buffer: Buffer }, string]> = [
      ["Isotipo (square mark)", { name: "mark.svg", mimeType: "image/svg+xml", buffer: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"/>') }, "Only PNG and WebP images are accepted."],
      ["Isotipo (square mark)", { name: "big.png", mimeType: "image/png", buffer: makePng(32, 32, [1, 2, 3], Buffer.alloc(300_000)) }, "The image is larger than the allowed size."],
      ["Isotipo (square mark)", { name: "fake.png", mimeType: "image/png", buffer: Buffer.from("<svg/> pretending to be a PNG") }, "Only PNG and WebP images are accepted."],
      ["Isotipo (square mark)", { name: "cut.png", mimeType: "image/png", buffer: makePng(64, 64).subarray(0, 60) }, "The image is malformed or outside the allowed dimensions."],
      ["Isotipo (square mark)", { name: "huge.png", mimeType: "image/png", buffer: makePng(2000, 2000) }, "The image is malformed or outside the allowed dimensions."],
      ["Isotipo (square mark)", { name: "tiny.png", mimeType: "image/png", buffer: makePng(8, 8) }, "The image is malformed or outside the allowed dimensions."],
    ];
    for (const [label, upload, message] of uploads) {
      await field(page, label).setInputFiles(upload);
      await expect(page.getByRole("alert")).toHaveText(message);
      await expect(page.getByText(/^Uploaded /)).toHaveCount(0);
    }
  });

  expect(await publicBranding(request, "org-a")).toEqual(before);
  expect(await page.locator("script:not([src])").count()).toBe(0);
  await signOut(page);
  expect(await violations()).toEqual([]);
});

test("a stale revision shows a reload prompt and the other administrator's save survives", async ({ page, request }) => {
  const violations = await watchViolations(page);
  await signIn(page, orgA.admin);
  await page.getByRole("button", { name: "Branding" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Branding" })).toBeVisible();
  const opened = await publicBranding(request, "org-a");
  await expect(page.getByText(`Revision ${opened.revision}`, { exact: true })).toBeVisible();

  // Another administrator (same account, API) saves first.
  const bearer = { Authorization: `Bearer ${await token(request, orgA.admin)}` };
  const theirs = {
    name: "Their Co",
    loginCopy: "",
    theme: { primary: "#7C3AED", accent: "#D97706", tint: "#FAE8D0", heading: "inter", body: "inter" },
    assets: {},
  };
  const theirSave = await request.put(`/forge/v1/orgs/${orgA.id}/branding`, {
    headers: bearer,
    data: { expectedRevision: opened.revision, branding: theirs },
  });
  expect(theirSave.status()).toBe(200);
  await revoke(request, bearer);

  await field(page, "Product name").fill("My Co");
  await page.getByRole("button", { name: "Save branding" }).click();
  await expect(page.getByRole("alert")).toHaveText(
    "The branding was changed by another administrator. Reload to see the latest version; nothing was overwritten.",
  );
  expect((await publicBranding(request, "org-a")).name).toBe("Their Co");

  await page.getByRole("button", { name: "Reload branding" }).click();
  await expect(field(page, "Product name")).toHaveValue("Their Co");
  await expect(page.getByText(`Revision ${opened.revision + 1}`, { exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(await rootVar(page, "--brand-teal")).toBe("#7C3AED");
  await signOut(page);
  expect(await violations()).toEqual([]);
});
