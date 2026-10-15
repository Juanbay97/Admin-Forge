import { ADMIN_BACKEND, expect, expectAccessible, expectNoHorizontalScroll, installBackend, test, viewports } from "./support";

const NEUTRAL = "If an account exists for that address, we sent a link to set a new password. Check your inbox.";

test.describe("forgot password", () => {
  test("the sign-in form links to it and it asks for the email once", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await page.getByRole("link", { name: "Forgot password?" }).click();
    await expect(page.getByRole("heading", { name: "Forgot your password?" })).toBeVisible();
    expect(new URL(page.url()).pathname).toBe("/admin/forgot-password");
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByRole("button", { name: "Send reset link" }).click();
    await expect(page.getByRole("status")).toContainText(NEUTRAL);
    const sent = api.requests.filter((request) => request.path.endsWith("/password-reset/request"));
    expect(sent).toHaveLength(1);
    expect(sent[0]?.method).toBe("POST");
    expect(sent[0]?.authorization).toBeNull();
  });

  test("an unknown address and a server failure show the very same confirmation", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.route("**/forge/v1/accounts/password-reset/request", (route) =>
      route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "SERVICE_UNAVAILABLE", message: "Unavailable.", request_id: "x", retryable: true } }) }),
    );
    await page.goto(`${adminUrl}forgot-password`);
    await page.getByLabel("Email").fill("nobody@example.com");
    await page.getByRole("button", { name: "Send reset link" }).click();
    await expect(page.getByRole("status")).toContainText(NEUTRAL);
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("an invalid address is refused before anything is sent, and the page can go back to sign in", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await page.goto(`${adminUrl}forgot-password`);
    await page.getByLabel("Email").fill("not-an-email");
    await page.getByRole("button", { name: "Send reset link" }).click();
    await expect(page.getByText("Enter a valid email address.")).toBeVisible();
    expect(api.requests.filter((request) => request.path.includes("password-reset"))).toEqual([]);
    await page.getByRole("link", { name: "Back to sign in" }).click();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });

  test("is accessible and fits every viewport", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(`${adminUrl}forgot-password`);
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});
