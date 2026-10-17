import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router";
import type { AreaManifest } from "./areas";

/** Area, then the current page; the last item carries aria-current. */
export function Breadcrumbs({ area }: { area: AreaManifest }) {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const entry = [...area.nav].sort((a, b) => b.to.length - a.to.length).find((item) => pathname === item.to || pathname.startsWith(`${item.to}/`));
  return (
    <nav aria-label={t("shell.breadcrumb")} className="min-w-0">
      <ol className="flex items-center gap-1.5 text-body text-muted">
        <li className="hidden sm:block">{t(area.labelKey)}</li>
        <li aria-hidden="true" className="hidden sm:block"><ChevronRight className="size-4" /></li>
        <li className="min-w-0 truncate">
          <span aria-current="page" className="font-medium text-fg">{entry ? t(entry.labelKey) : t("shell.notFoundCrumb")}</span>
        </li>
      </ol>
    </nav>
  );
}