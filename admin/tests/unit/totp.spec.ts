import { expect, test } from "@playwright/test";
import { base32Decode, nextCode, totpCode } from "../../e2e/support/totp";

// RFC 6238 appendix B, SHA-1, secret "12345678901234567890", 8 digits.
const RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ";

test.describe("TOTP helper (RFC 6238)", () => {
  test("matches the RFC vectors", () => {
    const vectors: Array<[number, string]> = [[59, "94287082"], [1111111109, "07081804"], [1111111111, "14050471"], [1234567890, "89005924"], [2000000000, "69279037"], [20000000000, "65353130"]];
    for (const [seconds, expected] of vectors) expect(totpCode(RFC_SECRET, { atSeconds: seconds, digits: 8 })).toBe(expected);
  });
  test("six digits by default, as the platform issues", () => {
    expect(totpCode(RFC_SECRET, { atSeconds: 59 })).toBe("287082");
  });
  test("base32 decodes without padding and rejects junk", () => {
    expect(base32Decode(RFC_SECRET).toString("ascii")).toBe("12345678901234567890");
    expect(() => base32Decode("not base32!")).toThrow();
  });
  test("a second login needs a newer step than the first (the server accepts each step once)", () => {
    const first = nextCode(RFC_SECRET, { lastStep: 0, nowSeconds: 59 });
    expect(first).toEqual({ step: 1, code: "287082", waitSeconds: 0 });
    const second = nextCode(RFC_SECRET, { lastStep: first.step, nowSeconds: 59 });
    expect(second.step).toBe(2);
    expect(second.waitSeconds).toBe(0); // one step ahead is inside the server window
    const third = nextCode(RFC_SECRET, { lastStep: second.step, nowSeconds: 59 });
    expect(third.step).toBe(3);
    expect(third.waitSeconds).toBe(1); // t=59 is step 1: step 3 is only acceptable once step 2 has begun at t=60
  });
});
