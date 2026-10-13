import { ChevronRight } from "lucide-react";
import { useLocation } from "react-router";
import type { AreaManifest } from "./areas";

/** Area, then the current page; the last item carries aria-current. */
export function Breadcrumbs({ area }: { area: AreaManifest }) {
  const { pathname } = useLocation();
  const entry = [...area.nav].sort((a, b) => b.to.length - a.to.length).find((item) => pathname === item.to || pathname.startsWith(`${item.to}/`));
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex items-center gap-1.5 text-body text-muted">
        <li className="hidden sm:block">{area.label}</li>
        <li aria-hidden="true" className="hidden sm:block"><ChevronRight className="size-4" /></li>
        <li className="min-w-0 truncate">
          <span aria-current="page" className="font-medium text-fg">{entry?.label ?? "Not found"}</span>
        </li>
      </ol>
    </nav>
  );
}