import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { Outlet } from "react-router";
import { applyBrandIdentity } from "../../brand/theme";
import { applyPlatformTheme, platformTheme } from "../../brand/platformTheme";
import { AREAS } from "../../shell/areas";
import { AppShell } from "../../shell/AppShell";
import { createIdleTimer } from "../../shell/idle";
import { IDLE_NOTICE, signOutWithNotice } from "../../shell/session";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { MfaGate } from "./mfa/MfaGate";

/**
 * The platform console. It always wears the fixed Prometheon theme (company branding is overwritten on entry and never applied
 * here), offers dark mode, shows a persistent badge, signs the owner out after 30 idle minutes and shows nothing but the second
 * factor until this session has passed it.
 */
export function PlatformLayout() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    applyPlatformTheme();
    applyBrandIdentity(platformTheme);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (dark) root.dataset.mode = "dark";
    else delete root.dataset.mode;
    return () => void delete root.dataset.mode;
  }, [dark]);

  useEffect(() => {
    const idle = createIdleTimer({ onIdle: () => signOutWithNotice(IDLE_NOTICE) });
    const events = ["keydown", "pointerdown", "pointermove", "wheel"] as const;
    events.forEach((name) => document.addEventListener(name, idle.touch, { passive: true }));
    return () => {
      idle.stop();
      events.forEach((name) => document.removeEventListener(name, idle.touch));
    };
  }, []);

  const switcher = (
    <>
      <Badge tone="info" className="hidden sm:inline-flex">Platform console</Badge>
      <Button variant="ghost" size="icon" aria-label={dark ? "Switch to light mode" : "Switch to dark mode"} aria-pressed={dark} onClick={() => setDark((value) => !value)}>
        {dark ? <Sun aria-hidden="true" className="size-5" /> : <Moon aria-hidden="true" className="size-5" />}
      </Button>
    </>
  );
  return (
    <MfaGate>
      <AppShell area={AREAS.platform} brand={platformTheme} switcher={switcher}>
        <Outlet />
      </AppShell>
    </MfaGate>
  );
}