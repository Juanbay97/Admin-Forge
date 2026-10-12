import { expect, test } from "@playwright/test";
import { applyVariables } from "../../src/brand/applier";

function fakeTarget() {
  const vars = new Map<string, string>();
  return { vars, target: { style: { setProperty: (name: string, value: string) => void vars.set(name, value) } } };
}

test.describe("variable applier", () => {
  test("writes plain colours and font stacks through setProperty", () => {
    const { vars, target } = fakeTarget();
    const ok = applyVariables(target, {
      "--brand-primary": "#0B1D26",
      "--border-subtle": "rgba(26, 26, 26, 0.08)",
      "--font-heading": '"Source Sans 3", "Segoe UI", system-ui, -apple-system, sans-serif',
    });
    expect(ok).toBe(true);
    expect(vars.size).toBe(3);
  });

  test("refuses a hostile value and then writes nothing at all", () => {
    for (const value of ["red; } body{display:none", "#12", "url(//evil.test/x)", "#0B1D26;color:red", "expression(1)", "#0B1D26 !important"]) {
      const { vars, target } = fakeTarget();
      expect(applyVariables(target, { "--brand-primary": "#0B1D26", "--brand-accent": value }), value).toBe(false);
      expect(vars.size).toBe(0);
    }
    const { vars, target } = fakeTarget();
    expect(applyVariables(target, { "--font-body": 'Inter"; } body{display:none' })).toBe(false);
    expect(applyVariables(target, { "--font-body": "url(//evil.test/f.woff2)" })).toBe(false);
    expect(vars.size).toBe(0);
  });

  test("refuses a property name that is not a custom property", () => {
    const { vars, target } = fakeTarget();
    expect(applyVariables(target, { background: "#000000" })).toBe(false);
    expect(applyVariables(target, { "--x;y": "#000000" })).toBe(false);
    expect(vars.size).toBe(0);
  });
});
