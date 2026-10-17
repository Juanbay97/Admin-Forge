import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { mfaStage } from "../../../platform/stage";
import { useServices } from "../../../shell/services";
import { Button } from "../../../ui/Button";
import { Spinner } from "../../../ui/Spinner";
import { PLATFORM_ME } from "../queries";
import { Enroll } from "./Enroll";
import { MfaPage } from "./MfaPage";
import { MfaStep } from "./MfaStep";

/**
 * Nothing under it renders (so no platform data is requested) until this session has passed the second factor. It re-reads the
 * platform identity every minute and whenever a call is refused with MFA_REQUIRED, so a stale verification sends the owner back to
 * the code step on the same URL.
 */
export function MfaGate({ children }: { children: ReactNode }) {
  const { t } = useTranslation(["platform", "common"]);
  const services = useServices();
  const client = useQueryClient();
  const [enrolling, setEnrolling] = useState(false);
  const me = useQuery({ queryKey: PLATFORM_ME, queryFn: () => services.platform.me(), staleTime: 0, refetchInterval: 60_000, retry: false });

  if (!me.data) {
    return me.isError ? (
      <MfaPage title={t("mfa.gate.errorTitle")} description={t("mfa.gate.errorDescription")}>
        <Button onClick={() => void me.refetch()}>{t("common:actions.tryAgain")}</Button>
      </MfaPage>
    ) : (
      <div className="p-8">
        <Spinner label={t("mfa.gate.checking")} />
      </div>
    );
  }
  const stage = mfaStage(me.data);
  if (enrolling || stage === "enroll") {
    return (
      <Enroll
        onBegin={() => setEnrolling(true)}
        onDone={() => {
          setEnrolling(false);
          void client.invalidateQueries({ queryKey: PLATFORM_ME });
        }}
      />
    );
  }
  if (stage === "ready") return <>{children}</>;
  return <MfaStep pending={stage === "confirm"} onStartOver={() => setEnrolling(true)} />;
}
