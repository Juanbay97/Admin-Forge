import { useTranslation } from "react-i18next";

// Deliberately generic: it must not reveal whether an organisation exists.
export function NotFound() {
  const { t } = useTranslation();
  return (
    <section className="flex flex-col gap-2">
      <h1 className="font-title text-page font-bold text-fg">{t("notFound.title")}</h1>
      <p className="text-body text-muted">{t("notFound.message")}</p>
    </section>
  );
}