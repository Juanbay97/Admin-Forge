import type { ReactNode } from "react";

/** One labelled figure of a summary; use inside a <dl>. */
export function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 rounded-card border border-line bg-surface p-5 shadow-card">
      <dt className="text-caption font-medium text-muted">{label}</dt>
      <dd className="flex min-h-8 items-center font-title text-section font-semibold text-fg">{children}</dd>
    </div>
  );
}