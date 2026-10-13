import { createHmac } from "node:crypto";

// RFC 6238 (HMAC-SHA1, 30 s steps) for the tests and the real-stack journeys. The platform accepts each step once and only one
// step either side of its clock, so a second login in the same half minute needs `nextCode`.
export const STEP_SECONDS = 30;
const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

export function base32Decode(text: string): Buffer {
  const clean = text.replace(/=+$/, "").toUpperCase();
  if (!/^[A-Z2-7]+$/.test(clean)) throw new Error("not base32");
  let bits = 0;
  let value = 0;
  const bytes: number[] = [];
  for (const char of clean) {
    value = (value << 5) | ALPHABET.indexOf(char);
    bits += 5;
    if (bits >= 8) {
      bits -= 8;
      bytes.push((value >>> bits) & 0xff);
    }
  }
  return Buffer.from(bytes);
}

export function hotp(secretBase32: string, counter: number, digits = 6): string {
  const message = Buffer.alloc(8);
  message.writeBigUInt64BE(BigInt(counter));
  const mac = createHmac("sha1", base32Decode(secretBase32)).update(message).digest();
  const offset = mac[mac.length - 1]! & 0x0f;
  const binary = ((mac[offset]! & 0x7f) << 24) | (mac[offset + 1]! << 16) | (mac[offset + 2]! << 8) | mac[offset + 3]!;
  return String(binary % 10 ** digits).padStart(digits, "0");
}

export function totpCode(secretBase32: string, { atSeconds = Date.now() / 1000, digits = 6 }: { atSeconds?: number; digits?: number } = {}): string {
  return hotp(secretBase32, Math.floor(atSeconds / STEP_SECONDS), digits);
}

/** The code for the first acceptable step after `lastStep`, and how long to wait before the server's window reaches it. */
export function nextCode(secretBase32: string, { lastStep, nowSeconds = Date.now() / 1000 }: { lastStep: number; nowSeconds?: number }) {
  const nowStep = Math.floor(nowSeconds / STEP_SECONDS);
  const step = Math.max(lastStep + 1, nowStep);
  const waitSeconds = Math.max(0, Math.ceil((step - 1) * STEP_SECONDS - nowSeconds));
  return { step, code: hotp(secretBase32, step), waitSeconds };
}
