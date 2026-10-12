import { useCallback, useEffect, useMemo, useState } from "react";
import type { BrandingApi } from "../api/branding";
import type { Branding } from "./branding";
import { applyBrandIdentity, applyBrandTheme, defaultTheme, themeFromBranding, type BrandTheme } from "./theme";

export type BrandState =
  | { orgId: string; status: "loading" }
  | { orgId: string; status: "error" }
  | { orgId: string; status: "ready"; branding: Branding };

/**
 * Loads the selected organization's branding and applies it to the shell (variables, title, favicon).
 * While another organization's branding is in flight the state is `loading` and the default look is
 * applied, so a previous organization's identity never outlives a switch. A failed load keeps the
 * default look; the console stays usable.
 */
export function useOrgBranding(api: BrandingApi, orgId: string) {
  const [loaded, setLoaded] = useState<BrandState>({ orgId, status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!orgId) return;
    let current = true;
    setLoaded({ orgId, status: "loading" });
    api.get(orgId).then(
      (branding) => current && setLoaded({ orgId, status: "ready", branding }),
      () => current && setLoaded({ orgId, status: "error" }),
    );
    return () => {
      current = false;
    };
  }, [api, orgId, attempt]);

  // A state left over from a previous organization is never shown as this one's.
  const state: BrandState = loaded.orgId === orgId ? loaded : { orgId, status: "loading" };
  const theme: BrandTheme = useMemo(
    () => (state.status === "ready" ? themeFromBranding(state.branding) : defaultTheme),
    [state],
  );

  useEffect(() => {
    applyBrandTheme(theme);
    applyBrandIdentity(theme);
  }, [theme]);
  // Signing out leaves the Prometheon look behind for the next person.
  useEffect(
    () => () => {
      applyBrandTheme(defaultTheme);
      applyBrandIdentity(defaultTheme);
    },
    [],
  );

  const replace = useCallback((branding: Branding) => setLoaded({ orgId, status: "ready", branding }), [orgId]);
  const reload = useCallback(() => setAttempt((count) => count + 1), []);
  return { state, theme, replace, reload };
}
