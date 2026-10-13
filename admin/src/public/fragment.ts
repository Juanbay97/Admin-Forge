// Private links carry their secret in the URL fragment, which no server or Referer header ever sees. The page reads it once into
// memory and then removes it from the address bar and history; nothing here stores or logs it.
const CAPABILITY = /^[A-Za-z0-9_-]{43}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** `#a=1&b=2` as a record, or null when a key repeats (an ambiguous link is not trusted). */
function pairs(hash: string): Record<string, string> | null {
  const text = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!text) return {};
  const found: Record<string, string> = {};
  for (const part of text.split("&")) {
    const [key = "", value = ""] = part.split("=");
    if (!key || key in found) return null;
    found[key] = value;
  }
  return found;
}

export function readCapability(hash: string): string | null {
  const found = pairs(hash);
  const keys = found ? Object.keys(found) : [];
  return found && keys.length === 1 && keys[0] === "capability" && CAPABILITY.test(found.capability ?? "") ? found.capability! : null;
}

export function readInvitation(hash: string): { invitationId: string; capability: string } | null {
  const found = pairs(hash);
  if (!found || Object.keys(found).sort().join() !== "capability,invitation_id") return null;
  return UUID.test(found.invitation_id!) && CAPABILITY.test(found.capability!) ? { invitationId: found.invitation_id!, capability: found.capability! } : null;
}

export function scrubFragment(history: Pick<History, "replaceState">, location: Pick<Location, "pathname" | "search">): void {
  history.replaceState(null, "", location.pathname + location.search);
}
