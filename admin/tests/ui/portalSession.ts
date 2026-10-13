import type { Page } from "@playwright/test";
import { expect } from "./support";
import { CAPABILITY, INVITATION, MEMBER, PASSWORD, installPortal, newPortalWorld, type PortalWorld } from "./portalSupport";

/** Joins through the real join page (the simplest way to hold a member session), ending on whatever the join page redirects to. */
export async function joinAndLand(page: Page, adminUrl: string, world: PortalWorld = newPortalWorld()) {
  const backend = await installPortal(page, world);
  await page.goto(`${adminUrl}join?c=acme#invitation_id=${INVITATION}&capability=${CAPABILITY}`);
  await page.getByLabel("Your email").fill(MEMBER.email);
  await page.getByLabel("New password", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Confirm password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create password and continue" }).click();
  await expect(page).toHaveURL(/\/admin\/portal/);
  return backend;
}