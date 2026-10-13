import { useEffect, useState } from "react";
import type { BrandingApi } from "../api/branding";
import type { Branding } from "../brand/branding";

export const BRANDING_WAIT_MS = 800;
const SLUG = /^[a-z0-9][a-z0-9-]{0,62}$/;

export type PublicBrand = { status: "loading" } | { status: "branded"; branding: Branding } | { status: "default" };

/**
 * The company's look before anyone signs in. A skeleton shows for at most 800 ms; after that the Prometheon default is used and,
 * if the branding arrives late, the page re-themes. A missing, malformed or unknown code is simply the default (never an error).
 */
export function usePublicBranding(api: Pick<BrandingApi, "getPublic">, code: string | null): PublicBrand {
  const valid = code !== null && SLUG.test(code);
  const [state, setState] = useState<PublicBrand>(valid ? { status: "loading" } : { status: "default" });

  useEffect(() => {
    if (!valid || code === null) {
      setState({ status: "default" });
      return;
    }
    let current = true;
    setState({ status: "loading" });
    const timer = setTimeout(() => current && setState((now) => (now.status === "loading" ? { status: "default" } : now)), BRANDING_WAIT_MS);
    api.getPublic(code).then(
      (branding) => current && setState(branding ? { status: "branded", branding } : { status: "default" }),
      () => current && setState({ status: "default" }),
    );
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [api, code, valid]);
  return state;
}