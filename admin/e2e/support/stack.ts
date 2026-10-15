import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { expect, type Page } from "@playwright/test";
import { nextCode } from "./totp";

// What the real-stack journeys share: where the owned stack keeps its private files, the platform owner's state (kept in that
// private workspace, deleted with it), screenshots, and the owner's password + TOTP sign-in.
function need(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is not set: run scripts\\admin-e2e.ps1.`);
  return value;
}

export const workspace = () => need("FORGE_E2E_WORKSPACE");
export const ownerLinkFile = () => need("FORGE_E2E_OWNER_LINK");
export const OWNER_EMAIL = "owner@platform.test";

export interface OwnerState {
  password: string;
  secret: string;
  lastStep: number;
  recoveryCodes: string[];
}

const stateFile = () => join(workspace(), "e2e-owner.json");
export const readOwner = (): OwnerState => JSON.parse(readFileSync(stateFile(), "utf8")) as OwnerState;
export const writeOwner = (state: OwnerState) => writeFileSync(stateFile(), JSON.stringify(state), "utf8");
export const ownerExists = () => existsSync(stateFile());

const shots = () => join(process.env.FORGE_E2E_SHOTS ?? join(process.env.TEMP ?? ".", "opencode", "forge-ui"));

/** Screenshots land in `<shots>/<area>/<name>.png`; they are evidence, never assertions. */
export async function shot(page: Page, area: "console" | "portal", name: string) {
  const directory = join(shots(), area);
  mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: join(directory, `${name}.png`), fullPage: false });
}

/** Passes the code step with the next acceptable TOTP step (the server accepts every step once) and records it. */
export async function passCodeStep(page: Page) {
  const owner = readOwner();
  const attempt = nextCode(owner.secret, { lastStep: owner.lastStep });
  if (attempt.waitSeconds > 0) await page.waitForTimeout(attempt.waitSeconds * 1000 + 250);
  await page.getByLabel("6-digit code").fill(attempt.code);
  await page.getByRole("button", { name: "Verify" }).click();
  writeOwner({ ...owner, lastStep: attempt.step });
}

/** Email + password + code, ending on the console. */
export async function signInOwner(page: Page, path = "/admin/platform") {
  const owner = readOwner();
  await page.goto(path);
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(owner.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Verify it is you" })).toBeVisible();
  await passCodeStep(page);
  await expect(page.getByRole("banner").getByText("Platform console").first()).toBeVisible();
}

/** Decodes a quoted-printable body (soft line breaks and =XX escapes) the way a mail client would. */
function unquote(text: string): string {
  return text.replace(/=\r?\n/g, "").replace(/=([0-9A-F]{2})/gi, (_, hex: string) => String.fromCharCode(parseInt(hex, 16)));
}

/** The newest local-mailbox message to `recipient`: its onboarding or set-password link, moved onto the control-plane origin. */
export function mailTo(recipient: string, only?: RegExp): { subject: string; link: string; path: string } {
  const directory = join(workspace(), "mailbox");
  const matches = readdirSync(directory)
    .filter((name) => name.endsWith(".eml"))
    .map((name) => ({ name, text: unquote(readFileSync(join(directory, name), "utf8")) }))
    .filter(({ text }) => new RegExp(`^To:.*${recipient.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`, "mi").test(text))
    // Message file names are random ids, so "the newest" is only meaningful within one kind of message: callers name it by subject.
    .filter(({ text }) => !only || only.test(/^Subject:\s*(.*)$/m.exec(text)?.[1] ?? ""));
  const last = matches.at(-1);
  if (!last) throw new Error(`no mailbox message for ${recipient}`);
  const link = /https?:\/\/[^\s"<>]+\/(?:onboarding|reset-password)[^\s"<>]*/.exec(last.text)?.[0];
  if (!link) throw new Error("the message carries no link");
  const subject = /^Subject:\s*(.*)$/m.exec(last.text)?.[1] ?? "";
  return { subject, link: link.replace(/^https?:\/\/[^/]+/, "http://127.0.0.1:3410"), path: join(directory, last.name) };
}

export interface CreatedCompanyState {
  id: string;
  slug: string;
  name: string;
  adminEmail: string;
}
const companyFile = () => join(workspace(), "e2e-company.json");
export const writeCompany = (state: CreatedCompanyState) => writeFileSync(companyFile(), JSON.stringify(state), "utf8");
export const readCompany = (): CreatedCompanyState => JSON.parse(readFileSync(companyFile(), "utf8")) as CreatedCompanyState;