import { expect, test } from "@playwright/test";
import { ensureCatalogue, meteredChat, seededOrg, tokenFor } from "./support/api";
import { shot, signInOwner } from "./support/stack";

// The platform console against the real stack, after 10-platform-owner created the owner. Each journey signs in with a password
// and the next TOTP step; usage comes from real metered chats through the fake gateway.
test.describe.configure({ mode: "serial" });

test("the overview shows real metered usage, the key pool and the audit trail", async ({ page, request }) => {
  const orgA = seededOrg("org-a");
  const alias = await ensureCatalogue(request, orgA.id, await tokenFor(request, orgA.admin));
  await meteredChat(request, orgA.id, await tokenFor(request, orgA.member), alias);

  await signInOwner(page);
  await expect(page.getByRole("heading", { level: 1, name: "Platform overview" })).toBeVisible();
  const kpis = page.getByRole("region", { name: "Key figures" });
  await expect(kpis.getByText("Companies")).toBeVisible();
  await expect(page.getByRole("figure").filter({ hasText: "Top companies by cost" }).getByTestId("bar-label").first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Gateway key pool" }).getByText(/active/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Recent activity" }).getByText("Second factor enrolled")).toBeVisible();
  await shot(page, "console", "10-overview");
  await page.getByRole("button", { name: "7 days" }).click();
  await expect(page).toHaveURL(/days=7/);
  await expect(page.getByRole("figure").filter({ hasText: "Tokens by model" }).getByTestId("bar-label").first()).toBeVisible();
  await page.getByRole("button", { name: "Switch to dark mode" }).click();
  await shot(page, "console", "11-overview-dark");
});
