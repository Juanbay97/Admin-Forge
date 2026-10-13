import { expect, test } from "@playwright/test";
import { describeAction, filterEntries, relativeTime } from "../../src/platform/audit";
import { changeOf, parseDays, previousWindow, windowFor } from "../../src/platform/range";
import { requestsOf, tokensOf } from "../../src/platform/usage";
import { dayPoints } from "../../src/platform/usage";

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

test.describe("daily series", () => {
  const day = (value: string, prompt: number, completion: number, cost: number) => ({ day: value, requests: prompt + completion > 0 ? 1 : 0, prompt_tokens: prompt, completion_tokens: completion, estimated_requests: 0, error_requests: 0, cost_micros: cost, unpriced_requests: 0, active_users: 1 });
  test("each UTC day becomes one point at midnight UTC, with tokens as prompt plus completion", () => {
    const points = dayPoints([day("2026-10-11", 500, 300, 18_000), day("2026-10-12", 700, 500, 24_000)]);
    expect(points.tokens).toEqual([{ t: Date.UTC(2026, 9, 11), v: 800 }, { t: Date.UTC(2026, 9, 12), v: 1200 }]);
    expect(points.cost).toEqual([{ t: Date.UTC(2026, 9, 11), v: 18_000 }, { t: Date.UTC(2026, 9, 12), v: 24_000 }]);
    expect(points.people).toEqual([{ t: Date.UTC(2026, 9, 11), v: 1 }, { t: Date.UTC(2026, 9, 12), v: 1 }]);
  });
  test("an empty series has no points and a series of only zero days is reported as empty", () => {
    expect(dayPoints([]).tokens).toEqual([]);
    expect(dayPoints([day("2026-10-11", 0, 0, 0)]).hasUsage).toBe(false);
    expect(dayPoints([day("2026-10-11", 0, 1, 0)]).hasUsage).toBe(true);
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

test.describe("audit filters and times", () => {
  const entry = (id: number, action: string, organization_id: string | null, recorded_at: string) => ({ id, actor_id: "a", action, organization_id, recorded_at });
  const entries = [
    entry(4, "company.suspended", "org-1", "2026-10-12T10:00:00Z"),
    entry(3, "gateway_key.created", null, "2026-10-11T10:00:00Z"),
    entry(2, "company.created", "org-2", "2026-10-10T10:00:00Z"),
    entry(1, "owner.mfa_enrolled", null, "2026-10-09T10:00:00Z"),
  ];
  test("no filter keeps everything, newest first as received", () => {
    expect(filterEntries(entries, { action: "", company: "", from: "", to: "" }).map((item) => item.id)).toEqual([4, 3, 2, 1]);
  });
  test("action and company narrow the list; a company filter excludes platform-wide events", () => {
    expect(filterEntries(entries, { action: "company.created", company: "", from: "", to: "" }).map((item) => item.id)).toEqual([2]);
    expect(filterEntries(entries, { action: "", company: "org-1", from: "", to: "" }).map((item) => item.id)).toEqual([4]);
  });
  test("the date range is inclusive of both UTC days", () => {
    expect(filterEntries(entries, { action: "", company: "", from: "2026-10-10", to: "2026-10-11" }).map((item) => item.id)).toEqual([3, 2]);
    expect(filterEntries(entries, { action: "", company: "", from: "2026-10-12", to: "" }).map((item) => item.id)).toEqual([4]);
  });
  test("relative times read naturally and fall back to the date for old events", () => {
    const now = new Date("2026-10-12T12:00:00Z");
    expect(relativeTime("2026-10-12T11:59:40Z", now)).toBe("just now");
    expect(relativeTime("2026-10-12T11:30:00Z", now)).toBe("30 minutes ago");
    expect(relativeTime("2026-10-12T09:00:00Z", now)).toBe("3 hours ago");
    expect(relativeTime("2026-10-11T12:00:00Z", now)).toBe("yesterday");
    expect(relativeTime("2026-10-08T12:00:00Z", now)).toBe("4 days ago");
    expect(relativeTime("2026-08-01T12:00:00Z", now)).toBe("Aug 1, 2026");
    expect(relativeTime("not a date", now)).toBe("—");
  });
});