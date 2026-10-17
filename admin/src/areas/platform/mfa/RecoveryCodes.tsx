import { Download, Printer } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { t as translate } from "../../../i18n/config";
import { Alert } from "../../../ui/Alert";
import { Button } from "../../../ui/Button";
import { Checkbox } from "../../../ui/Choice";
import { CopyButton } from "../../../ui/CopyButton";
import { MfaPage } from "./MfaPage";

export const RECOVERY_FILE = "forge-recovery-codes.txt";

function save(codes: string[]) {
  const url = URL.createObjectURL(new Blob([`${translate("platform:mfa.recovery.fileHeader")}\n\n${codes.join("\n")}\n`], { type: "text/plain" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = RECOVERY_FILE;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** Shown exactly once: copy, download or print them, then tick the box to go on. Nothing here is kept after Continue. */
export function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const { t } = useTranslation(["platform", "common"]);
  const [stored, setStored] = useState(false);
  return (
    <MfaPage title={t("mfa.recovery.title")} description={t("mfa.recovery.description")}>
      <Alert tone="warning">{t("mfa.recovery.warning")}</Alert>
      <ul aria-label={t("mfa.recovery.list")} className="grid grid-cols-1 gap-2 rounded-card border border-line bg-subtle p-4 font-mono text-body sm:grid-cols-2">
        {codes.map((code) => (
          <li key={code} className="select-all">{code}</li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <CopyButton value={codes.join("\n")} label={t("mfa.recovery.copy")} />
        <Button variant="outline" size="sm" onClick={() => save(codes)}>
          <Download aria-hidden="true" className="size-4" />
          {t("mfa.recovery.download")}
        </Button>
        <Button variant="outline" size="sm" onClick={() => window.print()}>
          <Printer aria-hidden="true" className="size-4" />
          {t("mfa.recovery.print")}
        </Button>
      </div>
      <Checkbox label={t("mfa.recovery.stored")} checked={stored} onCheckedChange={(value) => setStored(value === true)} />
      <Button size="lg" disabled={!stored} onClick={onDone}>
        {t("mfa.recovery.continue")}
      </Button>
    </MfaPage>
  );
}
