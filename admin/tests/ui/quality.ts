// Quality gates shared by every UI spec: no CSP violation, no serious/critical a11y violation, no horizontal scroll.
// `support.ts` installs the CSP watch for every test automatically; specs call the `expect*` helpers explicitly at the
// points that matter (after opening an overlay, on each viewport, in each theme).
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

/** The three layouts every routed page is checked at. */
export const viewports = {
  mobile: { width: 375, height: 812 },
  tablet: { width: 768, height: 1024 },
  desktop: { width: 1280, height: 800 },
} as const;

export interface CspWatch {
  /** Every `securitypolicyviolation` event and every console message about the Content Security Policy. */
  readonly violations: string[];
}

const REPORTER = "__forgeReportCspViolation";

/** Starts listening before any navigation; the page reports across reloads and route changes. */
export async function watchCsp(page: Page): Promise<CspWatch> {
  const violations: string[] = [];
  await page.exposeFunction(REPORTER, (entry: string) => void violations.push(entry));
  await page.addInitScript((reporter: string) => {
    document.addEventListener("securitypolicyviolation", (event) => {
      const report = (window as unknown as Record<string, (entry: string) => void>)[reporter];
      report?.(`${event.violatedDirective} blocked ${event.blockedURI || "inline"}`);
    });
  }, REPORTER);
  page.on("console", (message) => {
    if (/content security policy/i.test(message.text())) violations.push(`console: ${message.text()}`);
  });
  return { violations };
}

export function expectNoCspViolations(watch: CspWatch): void {
  expect(watch.violations, "CSP violations recorded while the page ran").toEqual([]);
}

/** axe with WCAG 2.0/2.1 A and AA rules; only serious and critical findings fail, minor ones stay visible in the message. */
export async function expectAccessible(page: Page, options: { scope?: string; exclude?: string[] } = {}): Promise<void> {
  let builder = new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]);
  if (options.scope) builder = builder.include(options.scope);
  for (const selector of options.exclude ?? []) builder = builder.exclude(selector);
  const { violations } = await builder.analyze();
  const blocking = violations
    .filter((violation) => violation.impact === "serious" || violation.impact === "critical")
    .map((violation) => `${violation.id} (${violation.impact}): ${violation.nodes.map((node) => node.target.join(" ")).join(" | ")}`);
  expect(blocking, "serious or critical accessibility violations").toEqual([]);
}

export async function expectNoHorizontalScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "document is wider than the viewport").toBeLessThanOrEqual(0);
}