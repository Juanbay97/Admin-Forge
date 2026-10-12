import type { Page } from "@playwright/test";
import { makePng } from "../png";
import { ADMIN_BACKEND, DEFAULT_BRANDING_FIXTURE, ORG_A, ORG_B, expect, installBackend, test } from "./support";

const ACME = {
  ...DEFAULT_BRANDING_FIXTURE,
  revision: 2,
  name: "Acme Labs",
  loginCopy: "Sign in to the Acme workspace.",
  theme: { primary: "#1D4ED8", accent: "#B45309", tint: "#E5E7EB", heading: "source-sans-3", body: "roboto" },
};
const rgb = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return `rgb(${r}, ${g}, ${b})`;
};

async function openBranding(page: Page, adminUrl: string, email = "admin@example.com") {
  await page.goto(adminUrl);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Sign in" }).click();
  if (email === "multi@example.com") await page.getByLabel("Organization").selectOption({ label: "Org A" });
  await page.getByRole("button", { name: "Branding" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Branding" })).toBeVisible();
}

const field = (page: Page, name: string) => page.getByLabel(name, { exact: true });
const rootVar = (page: Page, name: string) => page.evaluate((n) => document.documentElement.style.getPropertyValue(n), name);
const previewButton = (page: Page, mode: "Light" | "Dark") =>
  page.getByRole("group", { name: `${mode} preview` }).getByTestId("preview-button");

test.describe("branding page", () => {
  test("loads the saved values and previews both modes from the shared generator", async ({ page, adminUrl }) => {
    await installBackend(page, { ...ADMIN_BACKEND, brandings: { [ORG_A]: structuredClone(ACME) } });
    await openBranding(page, adminUrl);
    await expect(field(page, "Product name")).toHaveValue("Acme Labs");
    await expect(field(page, "Login message")).toHaveValue("Sign in to the Acme workspace.");
    await expect(field(page, "Primary color")).toHaveValue("#1D4ED8");
    await expect(field(page, "Heading font")).toHaveValue("source-sans-3");
    await expect(page.getByText("Revision 2")).toBeVisible();
    // Golden vector "blue, amber, cool grey tint": light #1D4ED8, dark #6183E4.
    await expect(previewButton(page, "Light")).toHaveCSS("background-color", rgb("#1D4ED8"));
    await expect(previewButton(page, "Dark")).toHaveCSS("background-color", rgb("#6183E4"));
    await expect(page.getByRole("group", { name: "Light preview" })).toContainText("Acme Labs");
  });

  test("the preview follows every edit while the page chrome waits for a save", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await openBranding(page, adminUrl);
    const chromeBefore = await rootVar(page, "--brand-teal");
    expect(chromeBefore).toBe("#0F6B6D");
    await field(page, "Primary color").fill("#7C3AED");
    await field(page, "Product name").fill("Violet Co");
    await expect(previewButton(page, "Light")).toHaveCSS("background-color", rgb("#7C3AED"));
    await expect(previewButton(page, "Dark")).toHaveCSS("background-color", rgb("#9D6BF2"));
    await expect(page.getByRole("group", { name: "Light preview" })).toContainText("Violet Co");
    expect(await rootVar(page, "--brand-teal")).toBe(chromeBefore);
    await expect(page.locator("header")).not.toContainText("Violet Co");
    expect(await page.title()).toBe("Prometheon Forge Admin");
  });

  test("an unreadable color combination is flagged in the preview and refused by the server's own message", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openBranding(page, adminUrl);
    await field(page, "Accent color").fill("#FFEB3B");
    await expect(page.getByTestId("preview-unavailable")).toBeVisible();
    // The shared generator flags it while typing, before any request is made.
    await expect(page.getByTestId("issue-accent")).toContainText("3:1");
    expect(api.requests.filter((r) => r.method === "PUT")).toHaveLength(0);
    await page.getByRole("button", { name: "Save branding" }).click();
    await expect(page.getByRole("alert")).toContainText("cannot produce a readable theme");
    expect(api.requests.filter((r) => r.method === "PUT")).toHaveLength(1);
    expect(api.branding(ORG_A)?.revision ?? 0).toBe(0);
  });

  test("a color problem is explained next to its field as you type and clears when fixed", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await openBranding(page, adminUrl);
    await expect(page.getByTestId("issue-primary")).toHaveCount(0);
    await field(page, "Primary color").fill("blue");
    await expect(page.getByTestId("issue-primary")).toContainText("hex color");
    await expect(field(page, "Primary color")).toHaveAttribute("aria-invalid", "true");
    await expect(field(page, "Primary color")).toHaveAccessibleDescription(/hex color/);
    await field(page, "Primary color").fill("#FFEB3B");
    await expect(page.getByTestId("issue-primary")).toContainText("3:1");
    await field(page, "Background tint").fill("#202020");
    await expect(page.getByTestId("issue-tint")).toContainText("lighter");
    await field(page, "Primary color").fill("#1D4ED8");
    await field(page, "Background tint").fill("#E5E7EB");
    await expect(page.getByTestId("issue-primary")).toHaveCount(0);
    await expect(page.getByTestId("issue-tint")).toHaveCount(0);
    await expect(field(page, "Primary color")).not.toHaveAttribute("aria-invalid", "true");
    await expect(page.getByTestId("preview-unavailable")).toHaveCount(0);
  });
  test("the preview shows the client sign-in screen as employees will see it", async ({ page, adminUrl }) => {
    await installBackend(page, { ...ADMIN_BACKEND, brandings: { [ORG_A]: structuredClone(ACME) } });
    await openBranding(page, adminUrl);
    for (const mode of ["Light", "Dark"]) {
      const pane = page.getByRole("group", { name: `${mode} preview` });
      await expect(pane.getByRole("heading", { name: "Welcome to Acme Labs" })).toBeVisible();
      await expect(pane).toContainText("Sign in to the Acme workspace.");
      await expect(pane).toContainText("Email address");
      await expect(pane).toContainText("Password");
      await expect(pane.getByTestId("preview-button")).toHaveText("Sign in");
    }
    await field(page, "Product name").fill("Violet Co");
    await field(page, "Login message").fill("Welcome back, team.");
    const light = page.getByRole("group", { name: "Light preview" });
    await expect(light.getByRole("heading", { name: "Welcome to Violet Co" })).toBeVisible();
    await expect(light).toContainText("Welcome back, team.");
    // The preview is a picture, not a form: it adds no inputs to the page.
    await expect(light.locator("input, button, a")).toHaveCount(0);
  });

  test("the preview shows the browser tab with the company name and favicon", async ({ page, adminUrl }) => {
    const sha = "c".repeat(64);
    await installBackend(page, { ...ADMIN_BACKEND, brandings: { [ORG_A]: structuredClone({ ...ACME, assets: { isotipo: sha } }) } });
    await openBranding(page, adminUrl);
    const tab = page.getByRole("group", { name: "Browser tab preview" });
    await expect(tab).toContainText("Acme Labs");
    await expect(tab.locator("img")).toHaveAttribute("src", `/forge/v1/branding/assets/${sha}`);
    await field(page, "Product name").fill("Violet Co");
    await expect(tab).toContainText("Violet Co");
    // The real tab does not change until the branding is saved.
    expect(await page.title()).toBe("Acme Labs Admin");
  });

  test("without an isotipo the tab preview shows the bundled default favicon", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await openBranding(page, adminUrl);
    const tab = page.getByRole("group", { name: "Browser tab preview" });
    await expect(tab).toContainText("Prometheon Forge");
    await expect(tab.locator("img")).toHaveAttribute("src", "/admin/brand/isotipo_claro.png");
  });
  test("saving publishes with the expected revision and re-themes the shell", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openBranding(page, adminUrl);
    await field(page, "Product name").fill("Violet Co");
    await field(page, "Primary color").fill("#7C3AED");
    await field(page, "Accent color").fill("#D97706");
    await field(page, "Background tint").fill("#FAE8D0");
    await field(page, "Heading font").selectOption("ibm-plex-sans");
    await field(page, "Body font").selectOption("nunito-sans");
    await page.getByRole("button", { name: "Save branding" }).click();

    await expect(page.getByRole("status").filter({ hasText: "Branding saved" })).toHaveText("Branding saved (revision 1).");
    expect(api.branding(ORG_A)).toMatchObject({ revision: 1, name: "Violet Co", theme: { primary: "#7C3AED", heading: "ibm-plex-sans" } });
    const put = api.requests.filter((r) => r.method === "PUT");
    expect(put.map((r) => r.path)).toEqual([`/forge/v1/orgs/${ORG_A}/branding`]);
    // Golden vector "saturated purple with warm tint": ink #251147, brand #7C3AED, accent #D97706, tint #FAE8D0.
    expect(await rootVar(page, "--brand-primary")).toBe("#251147");
    expect(await rootVar(page, "--brand-teal")).toBe("#7C3AED");
    expect(await rootVar(page, "--brand-accent")).toBe("#D97706");
    expect(await rootVar(page, "--brand-sand")).toBe("#FAE8D0");
    expect(await rootVar(page, "--brand-font-title")).toBe('"IBM Plex Sans", system-ui, sans-serif');
    await expect(page.locator("header")).toContainText("Violet Co");
    expect(await page.title()).toBe("Violet Co Admin");
  });

  test("a stale revision shows a reload prompt and overwrites nothing", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openBranding(page, adminUrl);
    api.bumpBranding(ORG_A);
    await field(page, "Product name").fill("Mine");
    await page.getByRole("button", { name: "Save branding" }).click();
    await expect(page.getByRole("alert")).toHaveText(
      "The branding was changed by another administrator. Reload to see the latest version; nothing was overwritten.",
    );
    expect(api.branding(ORG_A)?.name).toBe("Changed Elsewhere");
    await page.getByRole("button", { name: "Reload branding" }).click();
    await expect(field(page, "Product name")).toHaveValue("Changed Elsewhere");
    await expect(page.getByText("Revision 1")).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("reset asks for confirmation, then restores the Prometheon default", async ({ page, adminUrl }) => {
    const api = await installBackend(page, { ...ADMIN_BACKEND, brandings: { [ORG_A]: structuredClone(ACME) } });
    await openBranding(page, adminUrl);
    expect(await rootVar(page, "--brand-teal")).toBe("#1D4ED8");
    await page.getByRole("button", { name: "Reset to default" }).click();
    await page.getByRole("button", { name: "Cancel" }).click();
    expect(api.branding(ORG_A)?.revision).toBe(2);
    await page.getByRole("button", { name: "Reset to default" }).click();
    await expect(page.getByText("Reset to the Prometheon default?")).toBeVisible();
    await page.getByRole("button", { name: "Confirm reset" }).click();
    await expect(page.getByRole("status").filter({ hasText: "reset" })).toHaveText("Branding reset to the Prometheon default (revision 3).");
    expect(api.branding(ORG_A)).toMatchObject({ revision: 3, name: "Prometheon Forge", theme: DEFAULT_BRANDING_FIXTURE.theme });
    await expect(field(page, "Product name")).toHaveValue("Prometheon Forge");
    expect(await rootVar(page, "--brand-teal")).toBe("#0F6B6D");
    expect(await rootVar(page, "--brand-primary")).toBe("#0B1D26");
    expect(await page.title()).toBe("Prometheon Forge Admin");
  });

  test("server refusals are shown inline and nothing is saved", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openBranding(page, adminUrl);
    const refusals: Array<[string, string, string]> = [
      ["Primary color", "#FFFF00", "The primary color must reach 3:1 contrast against white."],
      ["Primary color", "red; } body{display:none", "A color must be a #RRGGBB hex value."],
      ["Product name", "}</style><script>alert(1)</script>", "The product name must be 1 to 40 plain characters."],
    ];
    for (const [label, value, message] of refusals) {
      await page.reload();
      await page.getByLabel("Email").fill("admin@example.com");
      await page.getByLabel("Password").fill("correct-horse-battery");
      await page.getByRole("button", { name: "Sign in" }).click();
      await page.getByRole("button", { name: "Branding" }).click();
      await field(page, label).fill(value);
      await page.getByRole("button", { name: "Save branding" }).click();
      await expect(page.getByRole("alert")).toHaveText(message);
      expect(api.branding(ORG_A)?.revision).toBe(0);
    }
    expect(await rootVar(page, "--brand-teal")).toBe("#0F6B6D");
  });

  test("a PNG upload previews locally, publishes on save, and an SVG or oversized file is refused", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openBranding(page, adminUrl);

    await field(page, "Isotipo (square mark)").setInputFiles({ name: "mark.svg", mimeType: "image/svg+xml", buffer: Buffer.from("<svg/>") });
    await expect(page.getByRole("alert")).toHaveText("Only PNG and WebP images are accepted.");
    const big = makePng(32, 32, [1, 2, 3], Buffer.alloc(300_000));
    await field(page, "Isotipo (square mark)").setInputFiles({ name: "big.png", mimeType: "image/png", buffer: big });
    await expect(page.getByRole("alert")).toHaveText("The image is larger than the allowed size.");

    await field(page, "Logo for light backgrounds").setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: makePng(64, 32) });
    await expect(page.getByText("Uploaded 64×32 px. It goes live when you save.")).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
    // Decoded locally (no blob: or data: URL, which the admin CSP forbids) and drawn on a canvas.
    await expect(page.getByRole("group", { name: "Light preview" }).locator("canvas")).toBeVisible();
    expect(await page.locator("img[src^='blob:'], img[src^='data:']").count()).toBe(0);
    expect(api.branding(ORG_A)?.assets).toEqual({});

    await page.getByRole("button", { name: "Save branding" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Branding saved" })).toBeVisible();
    const stored = api.branding(ORG_A)?.assets;
    expect(Object.keys(stored ?? {})).toEqual(["logoLight"]);
    // The shell now serves the published logo from the same origin.
    await expect(page.locator("header img")).toHaveAttribute("src", `/forge/v1/branding/assets/${stored?.logoLight}`);
    await expect.poll(() => page.locator("header img").evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(64);

    await page.getByRole("button", { name: "Remove logo for light backgrounds" }).click();
    await page.getByRole("button", { name: "Save branding" }).click();
    await expect(page.getByText("Revision 2", { exact: true })).toBeVisible();
    expect(api.branding(ORG_A)?.assets).toEqual({});
  });
});

test.describe("themed shell", () => {
  test("switching organizations replaces the previous theme before the next organization's data renders", async ({ page, adminUrl }) => {
    const api = await installBackend(page, {
      ...ADMIN_BACKEND,
      brandings: {
        [ORG_A]: structuredClone(ACME),
        [ORG_B]: { ...structuredClone(DEFAULT_BRANDING_FIXTURE), revision: 1, name: "Globex", theme: { primary: "#7C3AED", accent: "#D97706", tint: "#FAE8D0", heading: "inter", body: "inter" } },
      },
    });
    await page.goto(adminUrl);
    await page.getByLabel("Email").fill("multi@example.com");
    await page.getByLabel("Password").fill("correct-horse-battery");
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.getByLabel("Organization").selectOption({ label: "Org A" });
    await expect(page.locator("header")).toContainText("Acme Labs");
    expect(await rootVar(page, "--brand-teal")).toBe("#1D4ED8");
    expect(await page.title()).toBe("Acme Labs Admin");

    api.holdBranding(ORG_B);
    await page.getByLabel("Organization").selectOption({ label: "Org B" });
    // While B's branding is in flight A's identity is gone and no page content renders.
    await expect(page.getByRole("status")).toHaveText("Loading branding…");
    expect(await rootVar(page, "--brand-teal")).toBe("#0F6B6D");
    expect(await page.title()).toBe("Prometheon Forge Admin");
    await expect(page.getByRole("heading", { level: 1, name: "Org B" })).toHaveCount(0);
    api.releaseBranding(ORG_B);
    await expect(page.getByRole("heading", { level: 1, name: "Org B" })).toBeVisible();
    await expect(page.locator("header")).toContainText("Globex");
    expect(await rootVar(page, "--brand-teal")).toBe("#7C3AED");
    expect(await page.title()).toBe("Globex Admin");
  });

  test("a branding load failure falls back to the default look instead of blocking the console", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.route("**/forge/v1/orgs/*/branding", (route) =>
      route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "SERVICE_UNAVAILABLE", message: "Unavailable." } }) }),
    );
    await page.goto(adminUrl);
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByLabel("Password").fill("correct-horse-battery");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();
    expect(await rootVar(page, "--brand-teal")).toBe("#0F6B6D");
    await page.getByRole("button", { name: "Branding" }).click();
    await expect(page.getByRole("alert")).toHaveText("Branding could not be loaded. Try again.");
    await expect(page.getByRole("button", { name: "Save branding" })).toHaveCount(0);
  });

  test("a hostile branding response is rejected whole and never reaches a style", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.route("**/forge/v1/orgs/*/branding", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          revision: 1,
          name: "Evil",
          loginCopy: "",
          theme: { primary: "red; } body{display:none", accent: "#E07A2D", tint: "#E8DCC1", heading: "inter", body: "inter" },
          assets: { logoLight: "https://evil.test/x.png" },
        }),
      }),
    );
    const foreign: string[] = [];
    await page.context().route((url) => url.hostname === "evil.test", (route) => {
      foreign.push(route.request().url());
      return route.abort();
    });
    await page.goto(adminUrl);
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByLabel("Password").fill("correct-horse-battery");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();
    await expect(page.locator("body")).toBeVisible();
    expect(await rootVar(page, "--brand-teal")).toBe("#0F6B6D");
    await expect(page.locator("header")).not.toContainText("Evil");
    expect(foreign).toEqual([]);
  });

  test("a themed, previewing page raises no CSP violation and creates no style element", async ({ page, adminUrl }) => {
    await installBackend(page, { ...ADMIN_BACKEND, brandings: { [ORG_A]: structuredClone(ACME) } });
    await page.addInitScript(() => {
      (window as unknown as { __csp: string[] }).__csp = [];
      document.addEventListener("securitypolicyviolation", (e) =>
        (window as unknown as { __csp: string[] }).__csp.push(`${e.violatedDirective} ${e.blockedURI}`),
      );
    });
    await openBranding(page, adminUrl);
    await field(page, "Primary color").fill("#7C3AED");
    await field(page, "Logo for dark backgrounds").setInputFiles({ name: "d.png", mimeType: "image/png", buffer: makePng(40, 40) });
    await expect(page.getByRole("group", { name: "Dark preview" }).locator("canvas")).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => (window as unknown as { __csp: string[] }).__csp)).toEqual([]);
    expect(await page.locator("style").count()).toBe(0);
    expect(await page.evaluate(() => document.adoptedStyleSheets.length)).toBe(0);
  });

  test("a customised theme downloads its own font from the same origin", async ({ page, adminUrl }) => {
    await installBackend(page, { ...ADMIN_BACKEND, brandings: { [ORG_A]: structuredClone(ACME) } });
    const fonts: string[] = [];
    page.on("response", (response) => response.url().endsWith(".woff2") && fonts.push(new URL(response.url()).pathname));
    await openBranding(page, adminUrl);
    await expect.poll(() => fonts).toContain("/admin/fonts/source-sans-3-latin-wght-normal.woff2");
    expect(fonts.every((path) => path.startsWith("/admin/fonts/"))).toBe(true);
  });
});
