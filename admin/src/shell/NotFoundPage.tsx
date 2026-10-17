import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { NotFound } from "../components/NotFound";
import { LanguageSwitch } from "../i18n/LanguageSwitch";
import { Button } from "../ui/Button";

/** Full-page not found for paths outside any shell; deliberately generic. */
export function NotFoundPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 p-6">
      <LanguageSwitch className="self-end" />
      <NotFound />
      <Button variant="outline" className="self-start" onClick={() => navigate("/")}>
        {t("shell.backToHome")}
      </Button>
    </main>
  );
}