import type { PlatformMe } from "../api/platform";

export type MfaStage = "enroll" | "confirm" | "challenge" | "ready";

/** Where the owner is in the second-factor journey; the console renders only at `ready`. */
export function mfaStage(me: Pick<PlatformMe, "mfa">): MfaStage {
  if (me.mfa.state === "none") return "enroll";
  if (me.mfa.state === "pending") return "confirm";
  return me.mfa.verified && me.mfa.fresh ? "ready" : "challenge";
}
