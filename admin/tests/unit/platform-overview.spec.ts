import { expect, test } from "@playwright/test";
import { describeAction } from "../../src/platform/audit";
import { changeOf, parseDays, previousWindow, windowFor } from "../../src/platform/range";
import { requestsOf, tokensOf } from "../../src/platform/usage";

const NOW = new Date("2026-10-12T23:30:00Z");

test.describe("range", () => {
  test("days default to 30 and only 7, 30 and 90 are accepted", () => {
    expect(parseDays(null)).toBe(30);
    expect(parseDays("7")).toBe(7);
    expect(parseDays("90")).toBe(90);
    for (const bad of ["", "0", "31", "abc", "30.5", "-7", "7 "]) expect(parseDays(bad), bad).toBe(30);
  });
  test("a window is inclusive UTC days ending today, and the previous one ends the day before it starts", () => {
    expect(windowFor(7, NOW)).toEqual({ from: "2026-10-06", to: "2026-10-12" });
    expect(windowFor(30, NOW)).toEqual({ from: "2026-09-13", to: "2026-10-12" });
    expect(previousWindow(7, NOW)).toEqual({ from: "2026-09-29", to: "2026-10-05" });
  });
  test("a window never straddles the UTC date line of the server", () => {
    expect(windowFor(7, new Date("2026-10-12T00:00:00Z")).to).toBe("2026-10-12");
    expect(windowFor(7, new Date("2026-10-11T23:59:59Z")).to).toBe("2026-10-11");
  });
  test("change against the previous period", () => {
    expect(changeOf(150, 100)).toEqual({ direction: "up", percent: 50 });
    expect(changeOf(50, 100)).toEqual({ direction: "down", percent: 50 });
    expect(changeOf(100, 100)).toEqual({ direction: "flat", percent: 0 });
    expect(changeOf(10, 0)).toEqual({ direction: "new", percent: null });
    expect(changeOf(0, 0)).toEqual({ direction: "flat", percent: 0 });
  });
});

test.describe("usage counters", () => {
  const counters = { requests: 5, prompt_tokens: 1000, completion_tokens: 250, estimated_requests: 0, error_requests: 0, cost_micros: 1, unpriced_requests: 0 };
  test("tokens are prompt plus completion", () => {
    expect(tokensOf(counters)).toBe(1250);
    expect(requestsOf(counters)).toBe(5);
  });
});

test.describe("audit labels", () => {
  test("every action the server records reads as a sentence; an unknown one is shown as-is", () => {
    expect(describeAction("company.created")).toBe("Company created");
    expect(describeAction("company.suspended")).toBe("Company suspended");
    expect(describeAction("company.reactivated")).toBe("Company reactivated");
    expect(describeAction("company.branding_saved")).toBe("Branding saved");
    expect(describeAction("company.gateway_assigned")).toBe("Gateway keys assigned");
    expect(describeAction("company.model_access_set")).toBe("Model access set");
    expect(describeAction("gateway_key.created")).toBe("Gateway key added");
    expect(describeAction("gateway_key.rotated")).toBe("Gateway key rotated");
    expect(describeAction("gateway_key.status_changed")).toBe("Gateway key enabled or disabled");
    expect(describeAction("model_price.set")).toBe("Model price set");
    expect(describeAction("owner.mfa_enrolled")).toBe("Second factor enrolled");
    expect(describeAction("owner.mfa_recovery_used")).toBe("Recovery code used");
    expect(describeAction("something.new")).toBe("something.new");
  });
});
