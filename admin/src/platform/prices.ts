import type { Price } from "../api/platform";
import { MAX_PRICE_MICROS, microsFromUsd } from "./money";

export interface PriceForm {
  model: string;
  input: string;
  output: string;
  /** `YYYY-MM-DD` or empty for "now". */
  effective: string;
}

export interface PriceRequest {
  upstream_id: string;
  input_micros: number;
  output_micros: number;
  effective_from?: string;
}

type Errors = Partial<Record<"model" | "input" | "output" | "effective", string>>;

const MAX_USD = MAX_PRICE_MICROS / 1_000_000;

export function buildPriceRequest(form: PriceForm, now: Date = new Date()): { ok: true; request: PriceRequest } | { ok: false; errors: Errors } {
  const errors: Errors = {};
  const model = form.model.trim();
  if (!/^[!-~]{1,255}$/.test(model)) errors.model = "Enter the model id exactly as the gateway names it (no spaces).";
  const input = microsFromUsd(form.input.trim());
  const output = microsFromUsd(form.output.trim());
  const rule = `Use a non-negative amount of at most 6 decimals and at most ${MAX_USD}.`;
  if (input === null) errors.input = rule;
  if (output === null) errors.output = rule;
  const today = now.toISOString().slice(0, 10);
  let effective: string | undefined;
  if (form.effective) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(form.effective) || Number.isNaN(Date.parse(form.effective))) errors.effective = "Enter a valid date.";
    else if (form.effective < today) errors.effective = "The date cannot be in the past.";
    else if (form.effective > today) effective = `${form.effective}T00:00:00+00:00`;
  }
  if (Object.keys(errors).length > 0 || input === null || output === null) return { ok: false, errors };
  return { ok: true, request: { upstream_id: model, input_micros: input, output_micros: output, ...(effective ? { effective_from: effective } : {}) } };
}

/** The newest version of every model, models in alphabetical order. */
export function latestPrices(prices: readonly Price[]): Price[] {
  const newest = new Map<string, Price>();
  for (const price of prices) {
    const known = newest.get(price.upstream_id);
    if (!known || price.version > known.version) newest.set(price.upstream_id, price);
  }
  return [...newest.values()].sort((a, b) => a.upstream_id.localeCompare(b.upstream_id));
}