import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { ApiError } from "../api/client";
import { defaultTheme } from "../brand/theme";
import { Alert } from "../ui/Alert";
import { Button } from "../ui/Button";
import { readCapability, scrubFragment } from "./fragment";
import { MIN_PASSWORD, PasswordForm } from "./PasswordForm";
import { PublicFrame } from "./PublicFrame";

/**
 * The page any account's set-password link lands on (a forgotten password, or the first one of a platform owner) (`/reset-password#capability=…`). The capability is read once into memory and
 * removed from the address bar; the password goes to the consume endpoint and is dropped. Never calls an authenticated endpoint.
 */
export function ResetPassword({ consume }: { consume: (capability: string, password: string) => Promise<void> }) {
  const [capability] = useState(() => {
    const found = readCapability(window.location.hash);
    scrubFragment(window.history, window.location);
    return found;
  });
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const { t } = useTranslation("public");

  if (!capability) {
    return (
      <PublicFrame brand={defaultTheme} title={t("reset.invalidTitle")} description={t("reset.invalidDescription")}>
        <Button onClick={() => navigate("/", { replace: true })}>{t("reset.goToSignIn")}</Button>
      </PublicFrame>
    );
  }
  if (done) {
    return (
      <PublicFrame brand={defaultTheme} title={t("reset.doneTitle")} description={t("reset.doneDescription")}>
        <Alert tone="success" title={t("reset.doneAlertTitle")}>
          {t("reset.doneAlert")}
        </Alert>
        <Button size="lg" onClick={() => navigate("/", { replace: true })}>
          {t("reset.continue")}
        </Button>
      </PublicFrame>
    );
  }
  return (
    <PublicFrame brand={defaultTheme} title={t("reset.title")} description={t("reset.description")}>
      <PasswordForm
        submitLabel={t("reset.submit")}
        error={error}
        onSubmit={async (password) => {
          setError(null);
          try {
            await consume(capability, password);
            setDone(true);
          } catch (failure) {
            const status = failure instanceof ApiError ? failure.status : 0;
            setError(status === 404 ? t("reset.linkGone") : status === 422 ? t("reset.rejected", { min: MIN_PASSWORD }) : t("reset.unavailable"));
          }
        }}
      />
    </PublicFrame>
  );
}
