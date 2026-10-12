import { expect, test } from "@playwright/test";
import { createBrandingApi, type BrandingDocument } from "../../src/api/branding";
import { ApiError, createApiClient } from "../../src/api/client";
import { createSession } from "../../src/auth/session";
import { ASSET_URL_PREFIX } from "../../src/brand/branding";

type Call = { url: string; init: RequestInit };
const SHA = "c".repeat(64);
const document: BrandingDocument = {
  name: "Acme",
  loginCopy: "Welcome.",
  theme: { primary: "#0B1D26", accent: "#E07A2D", tint: "#E8DCC1", heading: "montserrat", body: "inter" },
  assets: { isotipo: SHA },
};
const served = (revision = 4) => ({
  revision,
  name: "Acme",
  loginCopy: "Welcome.",
  theme: document.theme,
  assets: { isotipo: ASSET_URL_PREFIX + SHA },
});

function api(respond: (call: Call) => Response) {
  const calls: Call[] = [];
  const session = createSession();
  session.set("tok");
  const fetchImpl = (async (url: string, init: RequestInit = {}) => {
    const call = { url, init };
    calls.push(call);
    return respond(call);
  }) as unknown as typeof fetch;
  return { calls, branding: createBrandingApi(createApiClient({ session, fetchImpl })) };
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

test.describe("branding api", () => {
  test("get reads the member projection and parses it", async () => {
    const { branding, calls } = api(() => json(200, served()));
    expect(await branding.get("org/one")).toEqual(served());
    expect(`${calls[0]?.init.method} ${calls[0]?.url}`).toBe("GET /forge/v1/orgs/org%2Fone/branding");
  });

  test("save puts the expected revision and the document and returns the new record", async () => {
    const { branding, calls } = api(() => json(200, served(5)));
    const saved = await branding.save("o1", 4, document);
    expect(saved.revision).toBe(5);
    expect(`${calls[0]?.init.method} ${calls[0]?.url}`).toBe("PUT /forge/v1/orgs/o1/branding");
    expect(JSON.parse(String(calls[0]?.init.body))).toEqual({ expectedRevision: 4, branding: document });
  });

  test("reset posts only the expected revision", async () => {
    const { branding, calls } = api(() => json(200, served(6)));
    expect((await branding.reset("o1", 5)).revision).toBe(6);
    expect(`${calls[0]?.init.method} ${calls[0]?.url}`).toBe("POST /forge/v1/orgs/o1/branding/reset");
    expect(JSON.parse(String(calls[0]?.init.body))).toEqual({ expectedRevision: 5 });
  });

  test("upload posts the raw bytes to the kind and returns the hash", async () => {
    const { branding, calls } = api(() =>
      json(201, { kind: "isotipo", sha256: SHA, url: ASSET_URL_PREFIX + SHA, contentType: "image/png", width: 241, height: 329 }),
    );
    const file = new Blob([new Uint8Array([1, 2, 3])], { type: "image/png" });
    expect(await branding.uploadAsset("o1", "isotipo", file)).toEqual({ sha256: SHA, width: 241, height: 329 });
    expect(`${calls[0]?.init.method} ${calls[0]?.url}`).toBe("POST /forge/v1/orgs/o1/branding/assets?kind=isotipo");
    expect(new Headers(calls[0]?.init.headers).get("Content-Type")).toBe("image/png");
    expect(calls[0]?.init.body).toBe(file);
  });

  test("an upload response that is not a content hash is refused", async () => {
    const { branding } = api(() => json(201, { kind: "isotipo", sha256: "../etc", url: "x", contentType: "image/png", width: 1, height: 1 }));
    const error = await branding.uploadAsset("o1", "isotipo", new Blob([new Uint8Array(1)], { type: "image/png" })).catch((e: unknown) => e);
    expect(error).toMatchObject({ code: "INVALID_RESPONSE" });
  });

  test("a hostile or malformed branding response becomes an invalid-response error, not a theme", async () => {
    const hostile = { ...served(), theme: { ...document.theme, primary: "red; } body{display:none" } };
    const { branding } = api(() => json(200, hostile));
    const error = await branding.get("o1").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 200, code: "INVALID_RESPONSE" });
  });

  test("server refusals keep the server message for display", async () => {
    const { branding } = api(() =>
      json(422, { error: { code: "INVALID_REQUEST", message: "The primary color must reach 3:1 contrast against white." } }),
    );
    const error = await branding.save("o1", 1, document).catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 422, message: "The primary color must reach 3:1 contrast against white." });
  });
});
