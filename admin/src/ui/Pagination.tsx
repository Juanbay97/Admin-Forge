import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "./Button";

export function Pagination({ page, pageCount, total, onPageChange }: { page: number; pageCount: number; total: number; onPageChange: (page: number) => void }) {
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-3 text-body text-muted">
      <span>{total} {total === 1 ? "result" : "results"}</span>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          <ChevronLeft aria-hidden="true" className="size-4" />
          Previous
        </Button>
        <span aria-live="polite" className="min-w-20 text-center text-fg">Page {page} of {pageCount}</span>
        <Button variant="outline" size="sm" disabled={page >= pageCount} onClick={() => onPageChange(page + 1)}>
          Next
          <ChevronRight aria-hidden="true" className="size-4" />
        </Button>
      </div>
    </nav>
  );
}