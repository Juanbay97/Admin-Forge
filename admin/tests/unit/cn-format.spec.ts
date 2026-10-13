import { expect, test } from "@playwright/test";
import { cn } from "../../src/lib/cn";
import { formatCostMicros, formatDate, formatPercent, formatTokens } from "../../src/lib/format";

test.describe("cn", () => {
  test("joins truthy classes and lets the last Tailwind utility win", () => {
    expect(cn("px-2 text-body", false && "hidden", undefined, "px-4")).toBe("text-body px-4");
    expect(cn("bg-action", { "opacity-50": true, "opacity-100": false })).toBe("bg-action opacity-50");
  });
});

test.describe("formatTokens", () => {
  test("abbreviates with one decimal", () => {
    expect(formatTokens(1_234_567)).toBe("1.2M");
    expect(formatTokens(1_234)).toBe("1.2K");
    expect(formatTokens(3_400_000_000)).toBe("3.4B");
    expect(formatTokens(98_000)).toBe("98K");
    expect(formatTokens(2_000_000)).toBe("2M");
  });
  test("keeps small numbers exact and survives zero and NaN", () => {
    expect(formatTokens(999)).toBe("999");
    expect(formatTokens(0)).toBe("0");
    expect(formatTokens(Number.NaN)).toBe("—");
  });
});

test.describe("formatCostMicros", () => {
  test("micro-dollars under one dollar keep four decimals", () => {
    expect(formatCostMicros(4_200)).toBe("$0.0042");
    expect(formatCostMicros(500_000)).toBe("$0.50");
  });
  test("a dollar or more groups thousands with two decimals", () => {
    expect(formatCostMicros(1_234_560_000)).toBe("$1,234.56");
    expect(formatCostMicros(1_500_000)).toBe("$1.50");
  });
  test("zero and NaN do not throw", () => {
    expect(formatCostMicros(0)).toBe("$0.00");
    expect(formatCostMicros(Number.NaN)).toBe("—");
  });
});

test.describe("formatPercent and formatDate", () => {
  test("formats a ratio with the requested precision", () => {
    expect(formatPercent(0.256)).toBe("26%");
    expect(formatPercent(0.256, 1)).toBe("25.6%");
    expect(formatPercent(Number.POSITIVE_INFINITY)).toBe("—");
  });
  test("dates render in UTC so they are stable across machines", () => {
    expect(formatDate("2026-10-12T23:30:00Z")).toBe("Oct 12, 2026");
    expect(formatDate("not a date")).toBe("—");
  });
});