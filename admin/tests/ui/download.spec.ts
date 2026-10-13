import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { newPortalWorld } from "./portalSupport";
import { joinAndLand } from "./portalSession";


const WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36";

test.describe("download page", () => {
  test.use({ userAgent: WINDOWS });

  test("shows the company code, the installer with version, size and date, and the verification hash", async ({ page, adminUrl }) => {
    await joinAndLand(page, adminUrl);
    await expect(page.getByRole("heading", { level: 1, name: "Get the app" })).toBeVisible();
    await expect(page.getByTestId("company-code")).toHaveText("acme");
    const download = page.getByRole("link", { name: "Download for Windows" });
    await expect(download).toHaveAttribute("href", "/downloads/Forge-Setup-1.2.3.exe");
    await expect(page.getByText("v1.2.3 · 86 MB")).toBeVisible();
    await expect(page.getByText("Released Oct 1, 2026")).toBeVisible();
    await page.getByText("Verify the download").click();
    await expect(page.getByTestId("sha256")).toHaveText("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
  });

  test("the deep link carries the origin and the code, and the manual fallback is always visible", async ({ page, adminUrl }) => {
    await joinAndLand(page, adminUrl);
    const open = page.getByRole("link", { name: "Open Forge" });
    const href = (await open.getAttribute("href")) ?? "";
    expect(href).toBe(`prometheon-forge://join?cp=${encodeURIComponent(new URL(page.url()).origin)}&code=acme`);
    await expect(page.getByText("Not opening? Enter code")).toBeVisible();
    await expect(page.getByText("SmartScreen")).toBeVisible();
  });

  test("copies the company code", async ({ page, adminUrl, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await joinAndLand(page, adminUrl);
    await page.getByRole("button", { name: "Copy code" }).click();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("acme");
  });

  test("an unpublished installer is explained and the code is still shown", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.manifest = null;
    await joinAndLand(page, adminUrl, world);
    await expect(page.getByText("The installer is not available yet")).toBeVisible();
    await expect(page.getByTestId("company-code")).toHaveText("acme");
    await expect(page.getByRole("link", { name: "Download for Windows" })).toHaveCount(0);
  });

  test("a manifest without a Windows installer reads as not published", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.manifest = { version: "1.0.0", released_at: "2026-10-01T00:00:00Z", platforms: {} };
    await joinAndLand(page, adminUrl, world);
    await expect(page.getByText("The installer is not available yet")).toBeVisible();
  });

  test("a manifest pointing off-origin is refused, never offered", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.manifest = { version: "1.0.0", released_at: "2026-10-01T00:00:00Z", platforms: { windows: { url: "https://evil.test/Forge.exe", sha256: "a".repeat(64), size_bytes: 1 } } };
    await joinAndLand(page, adminUrl, world);
    await expect(page.getByText("The installer is not available yet")).toBeVisible();
    await expect(page.locator('a[href*="evil.test"]')).toHaveCount(0);
  });

  test("is accessible and fits every viewport, light theme", async ({ page, adminUrl }) => {
    await joinAndLand(page, adminUrl);
    await expect(page.getByRole("link", { name: "Download for Windows" })).toBeVisible();
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});

test.describe("download page on another system", () => {
  test.use({ userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Safari/605.1.15" });
  test("says Windows only for now instead of offering a file that would not run", async ({ page, adminUrl }) => {
    await joinAndLand(page, adminUrl);
    await expect(page.getByText("Windows only for now")).toBeVisible();
    await expect(page.getByText(/You are on macOS/)).toBeVisible();
    await expect(page.getByRole("link", { name: "Download for Windows" })).toHaveCount(0);
    await expect(page.getByTestId("company-code")).toHaveText("acme");
  });
});
