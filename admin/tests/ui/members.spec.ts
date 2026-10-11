import type { Page } from "@playwright/test";
import { ADMIN_BACKEND, ORG_A, ORG_B, expect, installBackend, test } from "./support";

async function openMembers(page: Page, adminUrl: string, email = "admin@example.com") {
  await page.goto(adminUrl);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Sign in" }).click();
  if (email === "multi@example.com") await page.getByLabel("Organization").selectOption({ label: "Org A" });
  await page.getByRole("button", { name: "Members" }).click();
}

const row = (page: Page, name: string) => page.getByRole("row").filter({ hasText: name });

test.describe("members list", () => {
  test("shows each member with role, status and department", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openMembers(page, adminUrl);
    await expect(page.getByRole("heading", { level: 1, name: "Members" })).toBeVisible();
    await expect(row(page, "Alex Admin")).toContainText("alex@example.com");
    await expect(row(page, "Alex Admin")).toContainText("Administrator");
    await expect(row(page, "Pat Member")).toContainText("Member");
    await expect(row(page, "Pat Member")).toContainText("Active");
    await expect(row(page, "Pat Member")).toContainText("Legal");
    expect(api.requests.map((r) => `${r.method} ${r.path}`)).toContain(`GET /forge/v1/orgs/${ORG_A}/members`);
  });

  test("a stale organization renders the generic not-found", async ({ page, adminUrl }) => {
    await installBackend(page, { ...ADMIN_BACKEND, members: {} });
    await openMembers(page, adminUrl);
    await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
    await expect(page.getByText("Pat Member")).toHaveCount(0);
  });

  test("switching organizations clears the member list before the next loads", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openMembers(page, adminUrl, "multi@example.com");
    await expect(row(page, "Pat Member")).toBeVisible();
    api.hold(ORG_B);
    await page.getByLabel("Organization").selectOption({ label: "Org B" });
    await expect(page.getByRole("status")).toHaveText("Loading members…");
    await expect(page.getByText("Pat Member")).toHaveCount(0);
    api.letThrough(ORG_B);
    await expect(row(page, "Cy Clerk")).toBeVisible();
    await expect(page.getByText("Pat Member")).toHaveCount(0);
  });
});

test.describe("suspend and reactivate", () => {
  test("suspends a member, then reactivates", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openMembers(page, adminUrl);
    await page.getByRole("button", { name: "Suspend Pat Member" }).click();
    await expect(row(page, "Pat Member")).toContainText("Suspended");
    await expect(page.getByRole("button", { name: "Suspend Pat Member" })).toHaveCount(0);
    await page.getByRole("button", { name: "Reactivate Pat Member" }).click();
    await expect(row(page, "Pat Member")).toContainText("Active");
    expect(api.requests.map((r) => `${r.method} ${r.path}`)).toEqual(
      expect.arrayContaining([
        `POST /forge/v1/orgs/${ORG_A}/members/m-pat/suspend`,
        `POST /forge/v1/orgs/${ORG_A}/members/m-pat/reactivate`,
      ]),
    );
  });

  test("the last administrator cannot be suspended and the list is unchanged", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await openMembers(page, adminUrl);
    await page.getByRole("button", { name: "Suspend Alex Admin" }).click();
    await expect(page.getByRole("alert")).toHaveText(
      "This is the last administrator. Make another member an administrator before suspending this one.",
    );
    await expect(row(page, "Alex Admin")).toContainText("Active");
    await expect(page.getByRole("button", { name: "Suspend Alex Admin" })).toBeEnabled();
  });
});

test.describe("invite", () => {
  test("invites an email into a department and lists it as invited", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openMembers(page, adminUrl);
    await page.getByRole("button", { name: "Invite member" }).click();
    const dialog = page.getByRole("dialog", { name: "Invite a member" });
    await dialog.getByLabel("Name").fill("New Hire");
    await dialog.getByLabel("Email").fill("new@example.com");
    await dialog.getByLabel("Department").selectOption({ label: "Legal" });
    await dialog.getByRole("button", { name: "Send invitation" }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByRole("status")).toHaveText("Invitation sent to new@example.com.");
    await expect(row(page, "New Hire")).toContainText("Invited");
    await expect(row(page, "New Hire")).toContainText("new@example.com");
    await expect(row(page, "New Hire")).toContainText("Legal");
    expect(api.invitations).toEqual([
      { organization_id: ORG_A, department_id: "d-legal", email: "new@example.com", name: "New Hire" },
    ]);
  });

  test("a rejected invitation keeps the dialog open with a redacted error", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await openMembers(page, adminUrl);
    await page.getByRole("button", { name: "Invite member" }).click();
    const dialog = page.getByRole("dialog", { name: "Invite a member" });
    await dialog.getByLabel("Name").fill("Bad Mail");
    await dialog.getByLabel("Email").fill("invalid@example.com");
    await dialog.getByRole("button", { name: "Send invitation" }).click();
    await expect(dialog.getByRole("alert")).toHaveText(
      "The invitation could not be sent. Check the name and email, then try again.",
    );
    await expect(page.getByRole("row").filter({ hasText: "Bad Mail" })).toHaveCount(0);
  });
});

test.describe("accessibility", () => {
  test("the invitation completes with the keyboard and escape returns focus", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openMembers(page, adminUrl);
    const invite = page.getByRole("button", { name: "Invite member" });
    await invite.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByLabel("Name")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(invite).toBeFocused();

    await page.keyboard.press("Enter");
    await page.keyboard.type("Key Board");
    await page.keyboard.press("Tab");
    await page.keyboard.type("keys@example.com");
    await page.keyboard.press("Enter"); // the first department is preselected
    await expect(row(page, "Key Board")).toContainText("Invited");
    expect(api.invitations).toHaveLength(1);
  });

  test("honors prefers-reduced-motion on the new controls", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await openMembers(page, adminUrl);
    const duration = () =>
      page.getByRole("button", { name: "Invite member" }).evaluate((el) => getComputedStyle(el).transitionDuration);
    expect(await duration()).not.toBe("0s");
    await page.emulateMedia({ reducedMotion: "reduce" });
    expect(await duration()).toBe("0s");
  });
});
