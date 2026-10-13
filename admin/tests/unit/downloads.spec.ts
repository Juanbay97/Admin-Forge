import { expect, test } from "@playwright/test";
import { createDownloadsApi, parseManifest } from "../../src/api/downloads";
import { deepLink, formatBytes, pickInstaller } from "../../src/portal/download";

const SHA = "0123456789abcdef".repeat(4);
const manifest = { version: "1.2.3", released_at: "2026-10-01T00:00:00Z", platforms: { windows: { url: "/downloads/Forge-Setup-1.2.3.exe", sha256: SHA, size_bytes: 90_177_536 } } };

test.describe("installer manifest", () => {
  test("accepts the published shape", () => {
    expect(parseManifest(manifest)?.platforms.windows?.url).toBe("/downloads/Forge-Setup-1.2.3.exe");
  });
  test("an empty platform list is valid (nothing published yet) but an off-origin or malformed entry is refused", () => {
    expect(parseManifest({ ...manifest, platforms: {} })?.platforms.windows).toBeUndefined();
    for (const url of ["https://evil.test/Forge.exe", "//evil.test/x", "/other/Forge.exe", "/downloads/../x.exe", "javascript:alert(1)", "/downloads/"]) {
      expect(parseManifest({ ...manifest, platforms: { windows: { ...manifest.platforms.windows, url } } }), url).toBeNull();
    }
    expect(parseManifest({ ...manifest, platforms: { windows: { ...manifest.platforms.windows, sha256: "XYZ" } } })).toBeNull();
    expect(parseManifest({ version: "1" })).toBeNull();
    expect(parseManifest(null)).toBeNull();
  });
  test("the client fetches the same-origin manifest without credentials; 404 and junk mean not published", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    const respond = (status: number, body: unknown) => (async (input: RequestInfo | URL, init?: RequestInit) => (calls.push([String(input), init]), new Response(JSON.stringify(body), { status }))) as typeof fetch;
    expect(await createDownloadsApi(respond(200, manifest)).latest()).toMatchObject({ version: "1.2.3" });
    expect(calls[0]?.[0]).toBe("/downloads/latest.json");
    expect(calls[0]?.[1]).toMatchObject({ credentials: "omit", referrerPolicy: "no-referrer", cache: "no-cache" });
    expect(await createDownloadsApi(respond(404, {})).latest()).toBeNull();
    expect(await createDownloadsApi(respond(200, { nope: true })).latest()).toBeNull();
    await expect(createDownloadsApi((async () => { throw new TypeError("offline"); }) as typeof fetch).latest()).rejects.toThrow();
  });
});

test.describe("what to offer", () => {
  const parsed = parseManifest(manifest)!;
  test("Windows gets the installer; other systems are told Windows only for now", () => {
    expect(pickInstaller(parsed, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130")).toMatchObject({ kind: "download", installer: { sha256: SHA } });
    expect(pickInstaller(parsed, "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Safari/605")).toEqual({ kind: "unsupported", system: "macOS" });
    expect(pickInstaller(parsed, "Mozilla/5.0 (X11; Linux x86_64) Firefox/130")).toEqual({ kind: "unsupported", system: "Linux" });
    expect(pickInstaller(parsed, "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari")).toEqual({ kind: "unsupported", system: "iOS" });
    expect(pickInstaller(parsed, "Mozilla/5.0 (Linux; Android 14) Chrome/130 Mobile")).toEqual({ kind: "unsupported", system: "Android" });
  });
  test("nothing published is reported as such, whatever the system", () => {
    expect(pickInstaller(parseManifest({ ...manifest, platforms: {} })!, "Windows NT 10.0")).toEqual({ kind: "none" });
    expect(pickInstaller(null, "Windows NT 10.0")).toEqual({ kind: "none" });
  });
  test("sizes read in MB", () => {
    expect(formatBytes(90_177_536)).toBe("86 MB");
    expect(formatBytes(1_500)).toBe("1.5 KB");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2_500_000_000)).toBe("2.3 GB");
  });
  test("the deep link carries the control plane origin and the company code, both encoded", () => {
    expect(deepLink("https://forge.example.test", "acme")).toBe("prometheon-forge://join?cp=https%3A%2F%2Fforge.example.test&code=acme");
    expect(deepLink("http://127.0.0.1:3410", "a-b")).toBe("prometheon-forge://join?cp=http%3A%2F%2F127.0.0.1%3A3410&code=a-b");
  });
});