import { LogOut, Menu, Search } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { BrandTheme } from "../brand/theme";
import { cn } from "../lib/cn";
import { Button } from "../ui/Button";
import { Sheet } from "../ui/overlay/Dialog";
import { navFor, type AreaManifest } from "./areas";
import { Breadcrumbs } from "./Breadcrumbs";
import { CommandPalette } from "./CommandPalette";
import { useIdentity } from "./IdentityBoundary";
import { useServices } from "./services";
import { signOut } from "./session";
import { SidebarContent } from "./Sidebar";
import { UserMenu } from "./UserMenu";

interface AppShellProps {
  area: AreaManifest;
  brand: Pick<BrandTheme, "name" | "assets">;
  /** Extra topbar controls, e.g. the company switcher. */
  switcher?: ReactNode;
  children: ReactNode;
}

/**
 * The chrome every area shares: skip link, sidebar (collapsible from 1024px, a drawer below), topbar with breadcrumbs,
 * command palette and user menu, and the `<main id="main">` landmark.
 */
export function AppShell({ area, brand, switcher, children }: AppShellProps) {
  const identity = useIdentity();
  const services = useServices();
  const nav = navFor(area, identity);
  const [collapsed, setCollapsed] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [palette, setPalette] = useState(false);
  const main = useRef<HTMLElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPalette((open) => !open);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const exit = () => void signOut(services);
  return (
    <div className="min-h-screen bg-app font-body text-body text-fg">
      <a
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          main.current?.focus();
        }}
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-control focus:bg-action focus:px-4 focus:py-2 focus:text-on-action"
      >
        Skip to content
      </a>
      <aside className={cn("fixed inset-y-0 left-0 z-30 hidden bg-nav lg:block", collapsed ? "w-16" : "w-64")}>
        <SidebarContent brand={brand} nav={nav} collapsed={collapsed} onToggleCollapsed={() => setCollapsed((value) => !value)} />
      </aside>
      <div className={collapsed ? "lg:pl-16" : "lg:pl-64"}>
        <div role="banner" className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-line bg-surface px-3 sm:gap-3 sm:px-6">
          <Button variant="ghost" size="icon" aria-label="Open navigation" className="lg:hidden" onClick={() => setDrawer(true)}>
            <Menu aria-hidden="true" className="size-5" />
          </Button>
          <Breadcrumbs area={area} />
          <div className="ml-auto flex items-center gap-2">
            {switcher}
            <Button variant="outline" size="sm" aria-keyshortcuts="Control+K Meta+K" aria-label="Search pages" onClick={() => setPalette(true)} className="px-2.5 sm:px-3">
              <Search aria-hidden="true" className="size-4" />
              <span className="hidden text-muted md:inline">Search</span>
              <kbd className="hidden rounded border border-line px-1.5 text-caption text-muted md:inline">Ctrl K</kbd>
            </Button>
            <UserMenu identity={identity} onSignOut={exit} />
            <Button variant="ghost" size="sm" onClick={exit} aria-label="Sign out">
              <LogOut aria-hidden="true" className="size-4" />
              <span className="hidden sm:inline">Sign out</span>
            </Button>
          </div>
        </div>
        <main id="main" ref={main} tabIndex={-1} className="mx-auto max-w-[1280px] p-4 outline-none sm:p-6">
          {children}
        </main>
      </div>
      <Sheet open={drawer} onOpenChange={setDrawer} title="Navigation" side="left" hideTitle bare className="bg-nav text-on-nav">
        <SidebarContent brand={brand} nav={nav} onNavigate={() => setDrawer(false)} />
      </Sheet>
      <CommandPalette open={palette} onOpenChange={setPalette} nav={nav} />
    </div>
  );
}