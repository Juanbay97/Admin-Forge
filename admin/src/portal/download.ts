import type { Installer, InstallerManifest } from "../api/downloads";
import type { InstallerConfig } from "../api/installer";

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

/** The configuration as the file the installer reads: pretty JSON with a trailing newline under a fixed name. */
export const configFile = (config: InstallerConfig): { filename: string; text: string } => ({ filename: "forge-install.json", text: JSON.stringify(config, null, 2) + "\n" });

/** Hands text to the browser as a file download (an object URL on the same origin, revoked straight away). */
export function saveTextFile(file: { filename: string; text: string }): void {
  const url = URL.createObjectURL(new Blob([file.text], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = file.filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
