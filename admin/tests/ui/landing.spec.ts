import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import type { Page } from "@playwright/test";

const MANIFEST = {
  version: "1.2.3",
  released_at: "2026-10-01T00:00:00Z",
  platforms: { windows: { url: "/downloads/Forge-Setup-1.2.3.exe", sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", size_bytes: 90177536 } },
};

async function landing(page: Page, adminUrl: string, manifest: "ok" | "missing" | "invalid" | "down" | "foreign") {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(new URL(request.url()).pathname));
  await page.route("**/downloads/latest.json", (route) => {
    if (manifest === "ok") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MANIFEST) });
    if (manifest === "foreign") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...MANIFEST, platforms: { windows: { ...MANIFEST.platforms.windows, url: "https://evil.example/Setup.exe" } } }) });
    if (manifest === "invalid") return route.fulfill({ status: 200, contentType: "application/json", body: "{not json" });
    if (manifest === "down") return route.abort("failed");
    return route.fulfill({ status: 404, body: "" });
  });
  // The control plane serves this file at the domain root; the test server serves the same file under the bundle path.
  await page.goto(adminUrl + "landing.html");
  return requests;
}

test.describe("public landing", () => {
  test("introduces the product, signs in through /admin and credits OpenYak under Apache-2.0", async ({ page, adminUrl }) => {
    const requests = await landing(page, adminUrl, "ok");
    await expect(page).toHaveTitle(/Prometheon Forge/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("AI");
    const signIn = page.getByRole("banner").getByRole("link", { name: "Sign in" });
    await expect(signIn).toHaveAttribute("href", "/admin/");
    await expect(page.getByRole("main").getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/admin/");
    const footer = page.getByRole("contentinfo");
    await expect(footer).toContainText("OpenYak");
    await expect(footer.getByRole("link", { name: "Apache License 2.0" })).toHaveAttribute("href", "https://www.apache.org/licenses/LICENSE-2.0");
    expect(requests.filter((path) => path.startsWith("/forge/"))).toEqual([]);
  });

  test("offers the Windows installer from latest.json with its version, size and checksum", async ({ page, adminUrl }) => {
    await landing(page, adminUrl, "ok");
    const section = page.getByRole("region", { name: "Download for Windows" });
    await expect(section.getByRole("link", { name: "Download for Windows" })).toHaveAttribute("href", "/downloads/Forge-Setup-1.2.3.exe");
    await expect(section.getByText("Version 1.2.3")).toBeVisible();
    await expect(section.getByText("86 MB")).toBeVisible();
    await expect(section.getByText("Released Oct 1, 2026")).toBeVisible();
    await expect(section.getByTestId("sha256")).toHaveText("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
  });

  for (const manifest of ["missing", "invalid", "foreign"] as const) {
    test(`degrades to a clear notice when the manifest is ${manifest}`, async ({ page, adminUrl }) => {
      await landing(page, adminUrl, manifest);
      const section = page.getByRole("region", { name: "Download for Windows" });
      await expect(section.getByText("The installer is not published yet")).toBeVisible();
      await expect(section.getByRole("link", { name: "Download for Windows" })).toHaveCount(0);
      await expect(page.getByRole("main").getByRole("link", { name: "Sign in" })).toBeVisible();
    });
  }

  test("a network failure offers a retry that recovers", async ({ page, adminUrl }) => {
    await landing(page, adminUrl, "down");
    const section = page.getByRole("region", { name: "Download for Windows" });
    await expect(section.getByText("The installer information could not be loaded")).toBeVisible();
    await page.unroute("**/downloads/latest.json");
    await page.route("**/downloads/latest.json", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MANIFEST) }));
    await section.getByRole("button", { name: "Try again" }).click();
    await expect(section.getByRole("link", { name: "Download for Windows" })).toBeVisible();
  });

  test("is accessible and fits every viewport in every state", async ({ page, adminUrl }) => {
    await landing(page, adminUrl, "ok");
    await expect(page.getByRole("link", { name: "Download for Windows" }).first()).toBeVisible();
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
    await page.unroute("**/downloads/latest.json");
    await page.route("**/downloads/latest.json", (route) => route.fulfill({ status: 404, body: "" }));
    await page.reload();
    await expect(page.getByText("The installer is not published yet")).toBeVisible();
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});
