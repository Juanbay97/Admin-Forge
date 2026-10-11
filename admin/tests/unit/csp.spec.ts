import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { ADMIN_CSP } from "../csp";

test("the test CSP matches the policy the control plane serves", () => {
  const source = readFileSync(new URL("../../../src/forge/admin_mount.py", import.meta.url), "utf8");
  const match = source.match(/ADMIN_CSP = \(([^)]*)\)/s);
  expect(match).not.toBeNull();
  const served = [...(match?.[1] ?? "").matchAll(/"([^"]*)"/g)].map((m) => m[1]).join("");
  expect(served).toBe(ADMIN_CSP);
});
