import { ChevronsLeft, ChevronsRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router";
import type { BrandTheme } from "../brand/theme";
import { cn } from "../lib/cn";
import type { NavEntry } from "./areas";
import { NavIcon } from "./icons";

interface SidebarProps {
  brand: Pick<BrandTheme, "name" | "assets">;
  nav: NavEntry[];
  /** Icons only (>= 1024px sidebar). The drawer is never collapsed. */
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  onNavigate?: () => void;
}

const isCurrent = (pathname: string, to: string, siblings: NavEntry[]) =>
  pathname === to || (pathname.startsWith(`${to}/`) && !siblings.some((other) => other.to.length > to.length && pathname.startsWith(other.to)));

/**
 * Navigation entries are buttons that navigate (the contract the pages and tests already had), each marking the current page
 * with aria-current. Labels stay in the accessibility tree when the sidebar collapses to icons.
 */
export function SidebarContent({ brand, nav, collapsed = false, onToggleCollapsed, onNavigate }: SidebarProps) {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  return (
    <div className="flex h-full flex-col text-on-nav">
      <header className={cn("flex h-14 shrink-0 items-center gap-3 border-b border-on-nav-muted/30 px-4", collapsed && "justify-center px-0")}>
        <img src={brand.assets.markOnDark} alt="" className="h-8 w-auto shrink-0" />
        <span className={cn("truncate font-title text-card font-bold", collapsed && "sr-only")}>{brand.name}</span>
      </header>
      <nav aria-label={t("shell.sections")} className="flex-1 overflow-y-auto p-3">
        <ul className="flex flex-col gap-1">
          {nav.map((entry) => {
            const current = isCurrent(pathname, entry.to, nav);
            return (
              <li key={entry.to}>
                <button
                  type="button"
                  aria-current={current ? "page" : undefined}
                  title={collapsed ? t(entry.labelKey) : undefined}
                  onClick={() => {
                    navigate(entry.to);
                    onNavigate?.();
                  }}
                  className={cn(
                    "flex h-11 w-full items-center gap-3 rounded-control px-3 text-body font-medium outline-focus transition-colors focus-visible:outline-2",
                    "hover:bg-nav-hover aria-[current=page]:bg-nav-hover aria-[current=page]:text-white",
                    collapsed && "justify-center px-0",
                  )}
                >
                  <NavIcon name={entry.icon} className="size-5 shrink-0" />
                  <span className={cn("truncate", collapsed && "sr-only")}>{t(entry.labelKey)}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
      {onToggleCollapsed && (
        <div className="shrink-0 border-t border-on-nav-muted/30 p-3">
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-label={collapsed ? t("shell.expandSidebar") : t("shell.collapseSidebar")}
            className={cn("flex h-10 w-full items-center gap-3 rounded-control px-3 text-body text-on-nav outline-focus hover:bg-nav-hover focus-visible:outline-2", collapsed && "justify-center px-0")}
          >
            {collapsed ? <ChevronsRight aria-hidden="true" className="size-5" /> : <ChevronsLeft aria-hidden="true" className="size-5" />}
            <span className={cn(collapsed && "sr-only")} aria-hidden="true">{t("shell.collapse")}</span>
          </button>
        </div>
      )}
    </div>
  );
}