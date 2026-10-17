import type { Page } from "@playwright/test";
import { resources } from "../../src/i18n/resources";
import { ADMIN_BACKEND, expect, expectAccessible, expectNoHorizontalScroll, installBackend, test, viewports } from "./support";
import { OWNER, installPlatform, newWorld } from "./platformSupport";

const STORAGE_KEY = "forge.admin.language";
const en = resources.en;
const es = resources.es;

const storedLanguage = (page: Page) => page.evaluate((key) => localStorage.getItem(key), STORAGE_KEY);
const documentLanguage = (page: Page) => page.evaluate(() => document.documentElement.lang);

async function signInCompany(page: Page, labels: { email: string; password: string; submit: string }) {
  await page.getByLabel(labels.email).fill("admin@example.com");
  await page.getByLabel(labels.password).fill("correct-horse-battery");
  await page.getByRole("button", { name: labels.submit }).click();
}

async function signInPlatform(page: Page, labels: { email: string; password: string; submit: string }) {
  await page.getByLabel(labels.email).fill(OWNER.email);
  await page.getByLabel(labels.password).fill(OWNER.password);
  await page.getByRole("button", { name: labels.submit }).click();
}

test.describe("language: the browser decides until the person chooses", () => {
  test("an English browser gets English and stores nothing", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await expect(page.getByRole("button", { name: en.public.login.submit })).toBeVisible();
    expect(await documentLanguage(page)).toBe("en");
    expect(await storedLanguage(page)).toBeNull();
  });

  test.describe("a Spanish browser", () => {
    test.use({ locale: "es-CO" });

    test("gets Spanish on the sign-in page and the document language follows", async ({ page, adminUrl }) => {
      await installBackend(page, ADMIN_BACKEND);
      await page.goto(adminUrl);
      await expect(page.getByRole("button", { name: es.public.login.submit })).toBeVisible();
      await expect(page.getByLabel(es.public.login.password)).toBeVisible();
      expect(await documentLanguage(page)).toBe("es");
      expect(await storedLanguage(page)).toBeNull(); // detection alone never writes
    });

    test("the switch overrides the browser, is remembered across reloads, and signed-in headings follow it", async ({ page, adminUrl }) => {
      await installBackend(page, ADMIN_BACKEND);
      await page.goto(adminUrl);
      await page.getByLabel(es.common.language.label).selectOption("en");
      await expect(page.getByRole("button", { name: en.public.login.submit })).toBeVisible();
      expect(await storedLanguage(page)).toBe("en");
      expect(await documentLanguage(page)).toBe("en");
      await page.reload();
      await expect(page.getByRole("button", { name: en.public.login.submit })).toBeVisible();

      await signInCompany(page, { email: en.public.login.email, password: en.public.login.password, submit: en.public.login.submit });
      await page.getByRole("button", { name: en.common.nav.company.members }).click();
      await expect(page.getByRole("heading", { level: 1, name: en.common.nav.company.members })).toBeVisible();
      await page.getByLabel(en.common.language.label).selectOption("es");
      await expect(page.getByRole("heading", { level: 1, name: es.company.members.title })).toBeVisible();
      expect(es.company.members.title).not.toBe(en.company.members.title);
      expect(await storedLanguage(page)).toBe("es");
      expect(await documentLanguage(page)).toBe("es");
    });
  });
});

test.describe("Spanish catalogues in the console", () => {
  test("the platform console reads Spanish after the switch", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.mfa.verified = true;
    await installPlatform(page, world);
    await page.goto(adminUrl + "platform");
    await signInPlatform(page, { email: en.public.login.email, password: en.public.login.password, submit: en.public.login.submit });
    await expect(page.getByRole("heading", { level: 1, name: en.platform.overview.title })).toBeVisible();

    await page.getByLabel(en.common.language.label).selectOption("es");
    await expect(page.getByRole("heading", { level: 1, name: es.platform.overview.title })).toBeVisible();
    await expect(page.getByRole("navigation", { name: es.common.shell.sections }).getByRole("button", { name: es.common.nav.platform.companies })).toBeVisible();
    await expect(page.getByRole("region", { name: es.platform.overview.keyFigures })).toBeVisible();
    expect(await documentLanguage(page)).toBe("es");

    await page.getByRole("navigation", { name: es.common.shell.sections }).getByRole("button", { name: es.common.nav.platform.audit }).click();
    await expect(page.getByRole("heading", { level: 1, name: es.platform.audit.title })).toBeVisible();
  });

  test("a company administrator reads Spanish from the first paint when the browser asks for it", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.addInitScript((key) => localStorage.setItem(key, "es"), STORAGE_KEY);
    await page.goto(adminUrl);
    await signInCompany(page, { email: es.public.login.email, password: es.public.login.password, submit: es.public.login.submit });
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();
    await expect(page.getByRole("region", { name: es.company.overview.summary })).toBeVisible();
    await page.getByRole("button", { name: es.common.nav.company.members }).click();
    await expect(page.getByRole("heading", { level: 1, name: es.company.members.title })).toBeVisible();
    await expect(page.getByRole("button", { name: es.company.members.invite })).toBeVisible();
  });

  test("Spanish copy is longer: pages still fit a phone and stay accessible", async ({ page, adminUrl }) => {
    test.setTimeout(90_000);
    await installBackend(page, ADMIN_BACKEND);
    await page.addInitScript((key) => localStorage.setItem(key, "es"), STORAGE_KEY);
    await page.goto(adminUrl);
    await expectAccessible(page); // the sign-in page, in Spanish
    await signInCompany(page, { email: es.public.login.email, password: es.public.login.password, submit: es.public.login.submit });
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();
    await page.getByRole("button", { name: es.common.nav.company.members }).click();
    await expect(page.getByRole("heading", { level: 1, name: es.company.members.title })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: es.common.shell.loading })).toHaveCount(0);
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});
