import type { ReactNode } from "react";
import type { BrandTheme } from "../brand/theme";
import { LanguageSwitch } from "../i18n/LanguageSwitch";
import { Card } from "../ui/Card";

/** The centred, signed-out page used by the join and set-password links; branded or Prometheon depending on `brand`. */
export function PublicFrame({ brand, eyebrow, title, description, children }: { brand: Pick<BrandTheme, "name" | "assets">; eyebrow?: ReactNode; title: string; description?: string; children?: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-lg flex-col justify-center gap-6 p-4 sm:p-6">
      <LanguageSwitch className="self-end" />
      <header className="flex items-center gap-4">
        <img src={brand.assets.markOnLight} alt="" className="h-12 w-auto max-w-40 object-contain" />
        <div className="flex min-w-0 flex-col items-start gap-1">
          {eyebrow}
          <p className="truncate font-title text-card font-semibold text-fg">{brand.name}</p>
        </div>
      </header>
      <Card>
        <div className="flex flex-col gap-5 p-5 sm:p-6">
          <div className="flex flex-col gap-1">
            <h1 className="font-title text-page font-bold text-fg">{title}</h1>
            {description && <p className="text-body text-muted">{description}</p>}
          </div>
          {children}
        </div>
      </Card>
    </main>
  );
}
