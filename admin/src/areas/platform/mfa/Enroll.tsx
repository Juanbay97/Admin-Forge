import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Enrollment } from "../../../api/platform";
import { QrCode } from "../../../components/qr/QrCode";
import { errorMessage } from "../../../shell/errors";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Button } from "../../../ui/Button";
import { CopyButton } from "../../../ui/CopyButton";
import { Field } from "../../../ui/Field";
import { Input } from "../../../ui/Input";
import { MfaPage } from "./MfaPage";
import { RecoveryCodes } from "./RecoveryCodes";

type Phase = { name: "intro" } | { name: "scan"; enrollment: Enrollment } | { name: "codes"; codes: string[] };

/**
 * Mandatory enrollment: start, scan the QR (or type the secret), confirm with a code, then save the recovery codes. The secret
 * and the codes live only in this component's state; leaving the step (`onDone`) unmounts them.
 */
export function Enroll({ onBegin, onDone }: { onBegin: () => void; onDone: () => void }) {
  const { t } = useTranslation(["platform", "common"]);
  const services = useServices();
  const [phase, setPhase] = useState<Phase>({ name: "intro" });
  const [code, setCode] = useState("");
  const start = useMutation({
    mutationFn: () => services.platform.enroll(),
    onSuccess: (enrollment) => {
      onBegin();
      setPhase({ name: "scan", enrollment });
    },
  });
  const confirm = useMutation({
    mutationFn: (value: string) => services.platform.verify({ code: value }),
    onSuccess: () => phase.name === "scan" && setPhase({ name: "codes", codes: phase.enrollment.recovery_codes }),
    onError: () => setCode(""),
  });

  if (phase.name === "codes") return <RecoveryCodes codes={phase.codes} onDone={onDone} />;
  if (phase.name === "intro") {
    return (
      <MfaPage title={t("mfa.enroll.introTitle")} description={t("mfa.enroll.introDescription")}>
        {start.isError && <Alert tone="destructive">{errorMessage(start.error)}</Alert>}
        <Button size="lg" loading={start.isPending} onClick={() => start.mutate()}>
          {t("mfa.enroll.start")}
        </Button>
      </MfaPage>
    );
  }
  const { enrollment } = phase;
  return (
    <MfaPage title={t("mfa.enroll.scanTitle")} description={t("mfa.enroll.scanDescription")}>
      <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
        <QrCode value={enrollment.otpauth_uri} label={t("mfa.enroll.qrLabel")} />
        <div className="flex min-w-0 flex-col gap-2">
          <p className="text-body text-muted">{t("mfa.enroll.cannotScan")}</p>
          <code className="break-all rounded-control bg-subtle px-3 py-2 font-mono text-body">{enrollment.secret}</code>
          <CopyButton value={enrollment.secret} label={t("mfa.enroll.copySecret")} />
        </div>
      </div>
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (/^\d{6}$/.test(code)) confirm.mutate(code);
        }}
      >
        <Field label={t("mfa.enroll.code")}>
          {(control) => <Input {...control} value={code} onChange={(event) => setCode(event.target.value.trim())} autoComplete="one-time-code" inputMode="numeric" maxLength={6} />}
        </Field>
        {confirm.isError && <Alert tone="destructive">{errorMessage(confirm.error)}</Alert>}
        <Button type="submit" size="lg" loading={confirm.isPending} disabled={!/^\d{6}$/.test(code)}>
          {t("mfa.enroll.confirm")}
        </Button>
      </form>
    </MfaPage>
  );
}
