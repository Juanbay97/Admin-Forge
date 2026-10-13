import { expect, test } from "@playwright/test";
import { buildPriceRequest, latestPrices } from "../../src/platform/prices";

const NOW = new Date("2026-10-12T15:00:00Z");

test.describe("price form", () => {
  test("USD per million tokens become integer micro-USD", () => {
    expect(buildPriceRequest({ model: "gpt-4o", input: "3.00", output: "15.00", effective: "" }, NOW)).toEqual({ ok: true, request: { upstream_id: "gpt-4o", input_micros: 3_000_000, output_micros: 15_000_000 } });
  });
  test("a future effective date is sent as midnight UTC; today or empty means now", () => {
    const future = buildPriceRequest({ model: "m", input: "1", output: "2", effective: "2026-11-01" }, NOW);
    expect(future).toEqual({ ok: true, request: { upstream_id: "m", input_micros: 1_000_000, output_micros: 2_000_000, effective_from: "2026-11-01T00:00:00+00:00" } });
    expect(buildPriceRequest({ model: "m", input: "1", output: "2", effective: "2026-10-12" }, NOW)).toMatchObject({ ok: true, request: { upstream_id: "m" } });
    expect((buildPriceRequest({ model: "m", input: "1", output: "2", effective: "2026-10-12" }, NOW) as { request: object }).request).not.toHaveProperty("effective_from");
  });
  test("each invalid field says what is wrong", () => {
    const refused = (input: Parameters<typeof buildPriceRequest>[0]) => (buildPriceRequest(input, NOW) as { ok: false; errors: Record<string, string> }).errors;
    expect(refused({ model: "", input: "1", output: "1", effective: "" }).model).toBeTruthy();
    expect(refused({ model: "has space", input: "1", output: "1", effective: "" }).model).toBeTruthy();
    expect(refused({ model: "m", input: "-1", output: "1", effective: "" }).input).toBeTruthy();
    expect(refused({ model: "m", input: "1", output: "1.0000001", effective: "" }).output).toBeTruthy();
    expect(refused({ model: "m", input: "1", output: "1001", effective: "" }).output).toContain("1000");
    expect(refused({ model: "m", input: "1", output: "1", effective: "2026-10-11" }).effective).toBeTruthy();
    expect(refused({ model: "m", input: "1", output: "1", effective: "soon" }).effective).toBeTruthy();
  });
});

test.describe("price list", () => {
  const price = (upstream_id: string, version: number, input_micros: number) => ({ id: version * 10, upstream_id, version, input_micros, output_micros: input_micros * 2, currency: "USD", effective_from: "2026-10-01T00:00:00+00:00", set_by: "x" });
  test("shows the newest version of each model, models in alphabetical order", () => {
    const latest = latestPrices([price("b", 1, 1), price("a", 1, 5), price("a", 3, 7), price("a", 2, 6)]);
    expect(latest.map((item) => [item.upstream_id, item.version])).toEqual([["a", 3], ["b", 1]]);
  });
});