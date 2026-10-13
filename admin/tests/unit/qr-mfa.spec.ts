import { expect, test } from "@playwright/test";
import { pathFromMatrix, qrFor } from "../../src/platform/qr";
import { mfaStage } from "../../src/platform/stage";

test.describe("QR as one SVG path", () => {
  test("a matrix becomes merged horizontal runs on a quiet-zone-free grid", () => {
    const matrix = [[true, true, false], [false, true, true], [false, false, false]];
    expect(pathFromMatrix(matrix)).toBe("M0 0h2v1h-2zM1 1h2v1h-2z");
  });
  test("an empty matrix is an empty path", () => {
    expect(pathFromMatrix([[false, false]])).toBe("");
  });
  test("a provisioning URI encodes to a square with the finder patterns in three corners", () => {
    const code = qrFor("otpauth://totp/Prometheon%20Forge:owner?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=Prometheon%20Forge");
    expect(code.size).toBeGreaterThanOrEqual(29);
    expect(code.path.startsWith("M0 0h7")).toBe(true); // top-left finder: seven dark modules in the first row
    expect(code.path).toMatch(/^[MhvzM0-9 \-]+$/); // nothing but path commands: no markup, no style
  });
});

test.describe("MFA stage", () => {
  const me = (state: "none" | "pending" | "active", verified: boolean) => ({ account_id: "a", role: "platform_owner" as const, mfa: { state, verified, fresh: verified } });
  test("an owner without a factor is sent to enrollment", () => expect(mfaStage(me("none", false))).toBe("enroll"));
  test("an unconfirmed enrollment asks for a code and offers to start over", () => expect(mfaStage(me("pending", false))).toBe("confirm"));
  test("an enrolled owner whose session has not passed the second factor is challenged", () => expect(mfaStage(me("active", false))).toBe("challenge"));
  test("a verified, fresh session enters the console", () => expect(mfaStage(me("active", true))).toBe("ready"));
  test("a verification older than the freshness window is challenged again, because changes would be refused", () => {
    expect(mfaStage({ mfa: { state: "active", verified: true, fresh: false } })).toBe("challenge");
  });
});
