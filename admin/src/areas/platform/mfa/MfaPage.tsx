import type { ReactNode } from "react";
import { platformTheme } from "../../../brand/platformTheme";
import { Badge } from "../../../ui/Badge";
import { Card } from "../../../ui/Card";

/** The centred page every pre-console step (code, enrollment, recovery codes) lives on. */
export function MfaPage({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-lg flex-col justify-center gap-6 p-4 sm:p-6">
      <header className="flex items-center gap-4">
        <img src={platformTheme.assets.markOnLight} alt="" className="h-12 w-auto" />
        <div className="flex flex-col items-start gap-1">
          <Badge tone="info">Platform console</Badge>
          <p className="font-title text-card font-semibold text-fg">{platformTheme.name}</p>
        </div>
      </header>
      <Card>
        <div className="flex flex-col gap-5 p-5 sm:p-6">
          <div className="flex flex-col gap-1">
            <h1 className="font-title text-page font-bold text-fg">{title}</h1>
            <p className="text-body text-muted">{description}</p>
          </div>
          {children}
        </div>
      </Card>
    </main>
  );
}
