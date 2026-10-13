import type { ReactNode } from "react";

/** The one h1 of a page, with an optional description and the page's primary action. */
export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="font-title text-page font-bold text-fg">{title}</h1>
        {description && <p className="text-body text-muted">{description}</p>}
      </div>
      {actions}
    </div>
  );
}