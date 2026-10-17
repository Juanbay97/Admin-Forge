import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../../api/client";
import { PLATFORM_ME } from "../queries";
import { useServices } from "../../../shell/services";
import { errorMessage } from "../../../shell/errors";
import { Alert } from "../../../ui/Alert";
import { Button } from "../../../ui/Button";
import { Field } from "../../../ui/Field";
import { Input } from "../../../ui/Input";
import { MfaPage } from "./MfaPage";

/** The second factor for an enrolled owner: a 6-digit code, or one of the recovery codes. */
export function MfaStep({ pending, onStartOver }: { pending: boolean; onStartOver: () => void }) {
  const { t } = useTranslation(["platform", "common"]);
  const services = useServices();
  const client = useQueryClient();
  const [recovery, setRecovery] = useState(false);
  const [value, setValue] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const verify = useMutation({
    mutationFn: (text: string) => services.platform.verify(recovery ? { recovery_code: text.trim() } : { code: text.trim() }),
    onSuccess: () => client.invalidateQueries({ queryKey: PLATFORM_ME }),
    onError: () => {
      setValue("");
      input.current?.focus();
    },
  });
  const locked = verify.error instanceof ApiError && verify.error.code === "MFA_LOCKED";
  const ready = recovery ? value.trim().length > 0 : /^\d{6}$/.test(value.trim());

  return (
    <MfaPage
      title={t("mfa.step.title")}
      description={recovery ? t("mfa.step.descriptionRecovery") : t("mfa.step.descriptionCode")}
    >
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (ready && !locked) verify.mutate(value);
        }}
      >
        <Field label={recovery ? t("mfa.step.recoveryCode") : t("mfa.step.code")}>
          {(control) => (
            <Input
              {...control}
              ref={input}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              disabled={locked}
              autoFocus
              autoComplete={recovery ? "off" : "one-time-code"}
              inputMode={recovery ? "text" : "numeric"}
              maxLength={recovery ? 64 : 6}
              spellCheck={false}
            />
          )}
        </Field>
        {verify.isError && <Alert tone="destructive">{errorMessage(verify.error)}</Alert>}
        <Button type="submit" size="lg" loading={verify.isPending} disabled={!ready || locked}>
          {t("mfa.step.verify")}
        </Button>
      </form>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        <Button
          variant="link"
          onClick={() => {
            setRecovery((current) => !current);
            setValue("");
            verify.reset();
          }}
        >
          {recovery ? t("mfa.step.useCode") : t("mfa.step.useRecovery")}
        </Button>
        {pending && (
          <Button variant="link" onClick={onStartOver}>
            {t("mfa.step.startOver")}
          </Button>
        )}
      </div>
    </MfaPage>
  );
}
