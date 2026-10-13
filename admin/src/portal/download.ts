import type { Installer, InstallerManifest } from "../api/downloads";

export type Offer = { kind: "download"; installer: Installer } | { kind: "unsupported"; system: string } | { kind: "none" };

function systemOf(userAgent: string): string | null {
  if (/Android/i.test(userAgent)) return "Android";
  if (/iPhone|iPad|iPod/i.test(userAgent)) return "iOS";
  if (/Windows/i.test(userAgent)) return null;
  if (/Macintosh|Mac OS X/i.test(userAgent)) return "macOS";
  if (/Linux|X11/i.test(userAgent)) return "Linux";
  return "this system";
}

/** The desktop app is Windows only for now; everyone else is told so instead of being offered a file that will not run. */
export function pickInstaller(manifest: InstallerManifest | null, userAgent: string): Offer {
  const installer = manifest?.platforms.windows;
  if (!installer) return { kind: "none" };
  const system = systemOf(userAgent);
  return system === null ? { kind: "download", installer } : { kind: "unsupported", system };
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units: Array<[number, string]> = [[1024 ** 3, "GB"], [1024 ** 2, "MB"], [1024, "KB"]];
  for (const [size, unit] of units) {
    if (bytes >= size) {
      const value = bytes / size;
      return `${unit === "MB" ? Math.round(value) : Number(value.toFixed(1))} ${unit}`;
    }
  }
  return `${bytes} B`;
}

/** Opens the desktop app on the right control plane and company: `prometheon-forge://join?cp=<origin>&code=<company code>`. */
export const deepLink = (origin: string, code: string): string => `prometheon-forge://join?cp=${encodeURIComponent(origin)}&code=${encodeURIComponent(code)}`;