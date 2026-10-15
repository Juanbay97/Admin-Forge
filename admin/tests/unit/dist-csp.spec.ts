// The production bundle (what `npm run build` ships to the control plane) must be CSP-clean on disk, and must not carry the
// test-only kit gallery. Built here with the same config into an ignored directory.
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { build } from "vite";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const OUT = path.join(ROOT, ".prod-dist");

test.describe("production bundle", () => {
  test.describe.configure({ mode: "serial" });
  let html = "";
  let scripts: string[] = [];
  let styles: string[] = [];

  test.beforeAll(async () => {
    test.setTimeout(180_000);
    delete process.env.VITE_KIT;
    await build({ root: ROOT, logLevel: "silent", build: { outDir: OUT, emptyOutDir: true } });
    html = readFileSync(path.join(OUT, "index.html"), "utf8");
    const assets = readdirSync(path.join(OUT, "assets"));
    scripts = assets.filter((name) => name.endsWith(".js")).map((name) => readFileSync(path.join(OUT, "assets", name), "utf8"));
    styles = assets.filter((name) => name.endsWith(".css")).map((name) => readFileSync(path.join(OUT, "assets", name), "utf8"));
  });

  test("index.html has no inline style, no inline script and only same-origin references", () => {
    expect(html).not.toMatch(/<style[\s>]/i);
    expect(html).not.toMatch(/\sstyle\s*=/i);
    expect(html).not.toMatch(/<script(?![^>]*\ssrc=)[^>]*>/i);
    expect([...html.matchAll(/(?:src|href)="([^"]+)"/g)].map((match) => match[1]).filter((url) => /^(?:https?:)?\/\//.test(url ?? ""))).toEqual([]);
  });

  // Scripts are deliberately not grepped for createElement("style"): React DOM (resource hoisting) and react-style-singleton
  // (behind react-remove-scroll, only reachable from the modal Radix variants the kit never uses) contain that call as dead code.
  // What proves the CSP at runtime is the automatic violation watch of every UI spec and the real-stack e2e.
  test("the stylesheet loads nothing remote and ships its fonts and marks from the same origin", () => {
    expect(styles.length).toBeGreaterThan(0);
    for (const css of styles) {
      expect(css).not.toMatch(/url\(\s*["']?(?:https?:)?\/\//i);
      expect(css).not.toMatch(/@import\s+(?:url\()?["']?https?:/i);
    }
  });

  test("landing.html is a second entry of the same bundle: no inline code, only /admin assets, no remote reference", () => {
    const landing = readFileSync(path.join(OUT, "landing.html"), "utf8");
    expect(landing).not.toMatch(/<style[\s>]/i);
    expect(landing).not.toMatch(/\sstyle\s*=/i);
    expect(landing).not.toMatch(/<script(?![^>]*\ssrc=)[^>]*>/i);
    const references = [...landing.matchAll(/(?:src|href)="([^"]+)"/g)].map((match) => match[1] ?? "");
    expect(references.filter((url) => /^(?:https?:)?\/\//.test(url))).toEqual([]);
    expect(references.length).toBeGreaterThan(0);
    for (const url of references) expect(url.startsWith("/admin/"), `${url} must stay under /admin/ so the edge forwards it`).toBe(true);
    expect(landing).toContain("<title>Prometheon Forge");
  });

  test("the kit gallery and the primitive spike are not shipped", () => {
    for (const js of scripts) {
      expect(js).not.toContain("Kit core");
      expect(js).not.toContain("Primitive spike");
      expect(js).not.toContain("Kit overlays and data");
    }
  });
});