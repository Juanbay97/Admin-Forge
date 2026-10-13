import { expect, test } from "@playwright/test";
import { readCapability, readInvitation, scrubFragment } from "../../src/public/fragment";

const CAP = "A".repeat(43);
const ID = "3f2c1a9e-8b7d-4c6a-9e5f-0a1b2c3d4e5f";

test.describe("link fragments", () => {
  test("a set-password link carries exactly one 43-character capability", () => {
    expect(readCapability(`#capability=${CAP}`)).toBe(CAP);
    for (const bad of ["", "#", "#capability=", `#capability=${CAP}x`, `#capability=short`, `#capability=${CAP}&capability=${CAP}`, `#other=${CAP}`, `#capability=${"%"}${CAP.slice(1)}`]) {
      expect(readCapability(bad), bad).toBeNull();
    }
  });
  test("an invitation carries a uuid and a capability, in any order, nothing else", () => {
    expect(readInvitation(`#invitation_id=${ID}&capability=${CAP}`)).toEqual({ invitationId: ID, capability: CAP });
    expect(readInvitation(`#capability=${CAP}&invitation_id=${ID}`)).toEqual({ invitationId: ID, capability: CAP });
    for (const bad of ["", `#capability=${CAP}`, `#invitation_id=${ID}`, `#invitation_id=nope&capability=${CAP}`, `#invitation_id=${ID}&capability=${CAP}&x=1`, `#invitation_id=${ID}&invitation_id=${ID}&capability=${CAP}`]) {
      expect(readInvitation(bad), bad).toBeNull();
    }
  });
  test("scrubbing replaces the URL with path and query only", () => {
    const calls: unknown[][] = [];
    scrubFragment({ replaceState: (...args: unknown[]) => void calls.push(args) }, { pathname: "/admin/join", search: "?c=acme" });
    expect(calls).toEqual([[null, "", "/admin/join?c=acme"]]);
  });
});
