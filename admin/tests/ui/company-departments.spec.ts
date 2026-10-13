import type { Page } from "@playwright/test";
import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { newPortalWorld, type PortalWorld } from "./portalSupport";
import { joinAndLand } from "./portalSession";

const go = (page: Page, path: string) =>
  page.evaluate((target) => {
    history.pushState(null, "", `/admin${target}`);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);

function world(): PortalWorld {
  const value = newPortalWorld();
  value.roles = ["organization_admin", "member"];
  value.departments = [{ id: "d-legal", name: "Legal" }, { id: "d-fin", name: "Finance" }];
  value.memberList = [
    { id: "m1", email: "alex@acme.test", display_name: "Alex Admin", status: "active", roles: ["organization_admin"], departments: [{ id: "d-legal", name: "Legal" }] },
    { id: "m2", email: "pat@acme.test", display_name: "Pat Member", status: "active", roles: ["member"], departments: [{ id: "d-fin", name: "Finance" }] },
  ];
  return value;
}

async function open(page: Page, adminUrl: string) {
  const backend = await joinAndLand(page, adminUrl, world());
  await go(page, "/company/members");
  await expect(page.getByRole("heading", { level: 1, name: "Members" })).toBeVisible();
  return backend;
}

test.describe("members and departments", () => {
  test("the people list filters by department", async ({ page, adminUrl }) => {
    await open(page, adminUrl);
    const table = page.getByRole("table", { name: "Members" });
    await expect(table.getByRole("row")).toHaveCount(3);
    await page.getByLabel("Department", { exact: true }).selectOption("Finance");
    await expect(table.getByRole("row")).toHaveCount(2);
    await expect(table.getByRole("row").nth(1)).toContainText("Pat Member");
  });

  test("an administrator moves a person to another department and the list shows it at once", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl);
    const table = page.getByRole("table", { name: "Members" });
    await table.getByRole("row", { name: /Pat Member/ }).getByRole("button", { name: /Change department/ }).click();
    const dialog = page.getByRole("dialog", { name: "Change department" });
    await expect(dialog.getByLabel("Department")).toHaveValue("d-fin"); // starts on the current department
    await dialog.getByLabel("Department").selectOption("Legal");
    await dialog.getByRole("button", { name: "Save department" }).click();
    await expect(dialog).toBeHidden();
    await expect(table.getByRole("row", { name: /Pat Member/ })).toContainText("Legal");
    await expect(table.getByRole("row", { name: /Pat Member/ })).not.toContainText("Finance");
    expect(requests.find((request) => request.method === "PUT" && request.path.endsWith("/members/m2/department"))?.body).toEqual({ department_id: "d-legal" });
  });

  test("a refused assignment is said in words and leaves the person where they were", async ({ page, adminUrl }) => {
    const { world: state } = await open(page, adminUrl);
    state.departments = state.departments.filter((department) => department.id !== "d-legal"); // gone on the server since the page loaded
    const table = page.getByRole("table", { name: "Members" });
    await table.getByRole("row", { name: /Pat Member/ }).getByRole("button", { name: /Change department/ }).click();
    const dialog = page.getByRole("dialog", { name: "Change department" });
    await dialog.getByLabel("Department").selectOption("Legal");
    await dialog.getByRole("button", { name: "Save department" }).click();
    await expect(dialog.getByRole("alert")).toContainText("could not be changed");
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(table.getByRole("row", { name: /Pat Member/ })).toContainText("Finance");
  });

  test("the Departments tab lists them and creates one that appears in the filter without a reload", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl);
    await page.getByRole("tab", { name: "Departments" }).click();
    const list = page.getByRole("list", { name: "Departments" });
    await expect(list.getByRole("listitem")).toHaveText(["Finance", "Legal"]);
    await page.getByLabel("New department").fill("Operations");
    await page.getByRole("button", { name: "Create department" }).click();
    await expect(list.getByRole("listitem")).toHaveText(["Finance", "Legal", "Operations"]);
    expect(requests.find((request) => request.method === "POST" && request.path.endsWith("/departments"))?.body).toEqual({ name: "Operations" });
    await page.getByRole("tab", { name: "People" }).click();
    await expect(page.getByLabel("Department", { exact: true }).locator("option")).toContainText(["All departments", "Finance", "Legal", "Operations"]);
  });

  test("a name that already exists is refused in words", async ({ page, adminUrl }) => {
    await open(page, adminUrl);
    await page.getByRole("tab", { name: "Departments" }).click();
    await page.getByLabel("New department").fill("Legal");
    await page.getByRole("button", { name: "Create department" }).click();
    await expect(page.getByRole("alert")).toContainText("already exists");
  });

  test("is accessible on every viewport", async ({ page, adminUrl }) => {
    await open(page, adminUrl);
    await page.getByRole("tab", { name: "Departments" }).click();
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});