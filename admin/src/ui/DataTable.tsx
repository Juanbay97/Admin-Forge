import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "../lib/cn";
import { Pagination } from "./Pagination";
import { Skeleton } from "./Skeleton";
import { nextSort, paginate, sortRows, type Sort } from "./table";

export interface Column<T> {
  id: string;
  header: string;
  cell: (row: T) => ReactNode;
  /** Makes the column sortable. */
  sortValue?: (row: T) => string | number | null;
  align?: "right";
  className?: string;
}

interface DataTableProps<T> {
  caption: string;
  columns: readonly Column<T>[];
  rows: readonly T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  loadingLabel?: string;
  /** Rendered instead of the table when there are no rows (an EmptyState). */
  empty: ReactNode;
  /** Search or filter controls above the table. */
  filter?: ReactNode;
  pageSize?: number;
  initialSort?: Sort | null;
  /** Caps the height so the header sticks while the body scrolls, e.g. "max-h-96". */
  scrollClassName?: string;
}

const SKELETON_ROWS = 5;

/** Sort, filter slot, pagination, sticky header, skeleton rows while loading and an empty state instead of an empty table. */
export function DataTable<T>({
  caption, columns, rows, rowKey, loading = false, loadingLabel, empty, filter, pageSize = 10, initialSort = null, scrollClassName,
}: DataTableProps<T>) {
  const { t, i18n } = useTranslation();
  const [sort, setSort] = useState<Sort | null>(initialSort);
  const [page, setPage] = useState(1);
  const sorted = useMemo(() => {
    const column = columns.find((candidate) => candidate.id === sort?.id);
    return sort && column?.sortValue ? sortRows(rows, column.sortValue, sort.direction) : rows;
  }, [columns, rows, sort]);
  const view = paginate(sorted, page, pageSize);
  const loadingText = loadingLabel ?? t("ui.table.loading", { caption: caption.toLocaleLowerCase(i18n.language) });

  return (
    <div className="flex flex-col gap-3">
      {filter}
      {loading ? (
        <div role="status" aria-label={loadingText} className="overflow-hidden rounded-card border border-line bg-surface">
          <span className="sr-only">{loadingText}</span>
          <Skeleton className="h-11 rounded-none" />
          {Array.from({ length: SKELETON_ROWS }, (_, index) => (
            <div key={index} className="flex h-11 items-center gap-4 border-t border-line px-4">
              {columns.map((column) => (
                <Skeleton key={column.id} className="h-4 flex-1" />
              ))}
            </div>
          ))}
        </div>
      ) : rows.length === 0 ? (
        empty
      ) : (
        <>
          <div
            role="region"
            aria-label={t("ui.table.scrollable")}
            tabIndex={0}
            className={cn("relative overflow-auto rounded-card border border-line bg-surface outline-focus focus-visible:outline-2", scrollClassName)}
          >
            <table className="w-full border-collapse text-left text-body">
              <caption className="sr-only">{caption}</caption>
              <thead>
                <tr>
                  {columns.map((column) => {
                    const active = sort?.id === column.id ? sort : null;
                    return (
                      <th
                        key={column.id}
                        scope="col"
                        aria-sort={column.sortValue ? (active ? (active.direction === "asc" ? "ascending" : "descending") : "none") : undefined}
                        className={cn("sticky top-0 z-10 h-11 whitespace-nowrap border-b border-line bg-subtle px-4 font-semibold text-fg", column.align === "right" && "text-right")}
                      >
                        {column.sortValue ? (
                          <button
                            type="button"
                            onClick={() => setSort((current) => nextSort(current, column.id))}
                            className="-mx-2 inline-flex min-h-10 items-center gap-1.5 rounded-control px-2 outline-focus hover:bg-surface focus-visible:outline-2"
                          >
                            {column.header}
                            {active ? (
                              active.direction === "asc" ? <ArrowUp aria-hidden="true" className="size-3.5" /> : <ArrowDown aria-hidden="true" className="size-3.5" />
                            ) : (
                              <ChevronsUpDown aria-hidden="true" className="size-3.5 text-muted" />
                            )}
                          </button>
                        ) : (
                          column.header
                        )}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {view.items.map((row) => (
                  <tr key={rowKey(row)} className="h-11 border-t border-line first:border-t-0 hover:bg-subtle">
                    {columns.map((column) => (
                      <td key={column.id} className={cn("px-4 align-middle", column.align === "right" && "text-right tabular-nums", column.className)}>
                        {column.cell(row)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={view.page} pageCount={view.pageCount} total={view.total} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}