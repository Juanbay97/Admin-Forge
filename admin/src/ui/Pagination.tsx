import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "./Button";

export function Pagination({ page, pageCount, total, onPageChange }: { page: number; pageCount: number; total: number; onPageChange: (page: number) => void }) {
  const { t } = useTranslation();
  return (
    <nav aria-label={t("ui.pagination.label")} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 text-body text-muted">
      <span>{t("ui.pagination.results", { count: total })}</span>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          <ChevronLeft aria-hidden="true" className="size-4" />
          {t("ui.pagination.previous")}
        </Button>
        <span aria-live="polite" className="min-w-20 text-center text-fg">{t("ui.pagination.page", { page, pageCount })}</span>
        <Button variant="outline" size="sm" disabled={page >= pageCount} onClick={() => onPageChange(page + 1)}>
          {t("ui.pagination.next")}
          <ChevronRight aria-hidden="true" className="size-4" />
        </Button>
      </div>
    </nav>
  );
}