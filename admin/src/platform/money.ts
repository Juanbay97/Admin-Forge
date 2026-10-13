// Money is integer micro-USD per million tokens (the server's unit, capped at 1000 USD). The price form speaks decimal USD
// strings; the conversion is string arithmetic so no float ever touches a price.
export const MAX_PRICE_MICROS = 1_000_000_000;
const DECIMAL = /^(\d{1,4})(?:\.(\d{1,6}))?$/;

/** "3.00" -> 3_000_000; null for anything that is not a non-negative decimal of at most six places within the cap. */
export function microsFromUsd(text: string): number | null {
  const match = DECIMAL.exec(text);
  if (!match) return null;
  const micros = Number(match[1]) * 1_000_000 + Number((match[2] ?? "").padEnd(6, "0"));
  return micros <= MAX_PRICE_MICROS ? micros : null;
}

/** 2_500_000 -> "2.50"; keeps up to six decimals when they are needed. */
export function usd(micros: number): string {
  const whole = Math.floor(micros / 1_000_000);
  const fraction = String(micros % 1_000_000).padStart(6, "0").replace(/0+$/, "").padEnd(2, "0");
  return `${whole}.${fraction}`;
}