import { ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LanguageSwitch } from "../i18n/LanguageSwitch";
import { Button } from "../ui/Button";

interface AccessDeniedProps {
  title?: string;
  message?: string;
  onSignOut: () => void;
}

export function AccessDenied({ title, message, onSignOut }: AccessDeniedProps) {
  const { t } = useTranslation();
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 p-6">
      <LanguageSwitch className="self-end" />
      <span className="flex size-12 items-center justify-center rounded-full bg-danger-soft text-on-danger-soft">
        <ShieldAlert aria-hidden="true" className="size-6" />
      </span>
      <h1 className="font-title text-page font-bold text-fg">{title ?? t("accessDenied.title")}</h1>
      <p className="text-body text-muted">{message ?? t("accessDenied.message")}</p>
      <Button className="self-start" onClick={onSignOut}>
        {t("shell.signOut")}
      </Button>
    </main>
  );
}