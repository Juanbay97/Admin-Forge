import { Download, Printer } from "lucide-react";
import { useState } from "react";
import { Alert } from "../../../ui/Alert";
import { Button } from "../../../ui/Button";
import { Checkbox } from "../../../ui/Choice";
import { CopyButton } from "../../../ui/CopyButton";
import { MfaPage } from "./MfaPage";

export const RECOVERY_FILE = "forge-recovery-codes.txt";

function save(codes: string[]) {
  const url = URL.createObjectURL(new Blob([`Prometheon Forge platform recovery codes\n\n${codes.join("\n")}\n`], { type: "text/plain" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = RECOVERY_FILE;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** Shown exactly once: copy, download or print them, then tick the box to go on. Nothing here is kept after Continue. */
export function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const [stored, setStored] = useState(false);
  return (
    <MfaPage title="Save your recovery codes" description="Each code opens the console once if you lose your authenticator. They are shown only now.">
      <Alert tone="warning">Store them somewhere safe, apart from this device. They cannot be shown again.</Alert>
      <ul aria-label="Recovery codes" className="grid grid-cols-1 gap-2 rounded-card border border-line bg-subtle p-4 font-mono text-body sm:grid-cols-2">
        {codes.map((code) => (
          <li key={code} className="select-all">{code}</li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <CopyButton value={codes.join("\n")} label="Copy codes" />
        <Button variant="outline" size="sm" onClick={() => save(codes)}>
          <Download aria-hidden="true" className="size-4" />
          Download
        </Button>
        <Button variant="outline" size="sm" onClick={() => window.print()}>
          <Printer aria-hidden="true" className="size-4" />
          Print
        </Button>
      </div>
      <Checkbox label="I stored them in a safe place" checked={stored} onCheckedChange={(value) => setStored(value === true)} />
      <Button size="lg" disabled={!stored} onClick={onDone}>
        Continue to the console
      </Button>
    </MfaPage>
  );
}
