import { useRef, useState } from "react";
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
      title="Verify it is you"
      description={recovery ? "Enter one of the recovery codes you saved. Each works once." : "Enter the 6-digit code from your authenticator app to open the console."}
    >
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (ready && !locked) verify.mutate(value);
        }}
      >
        <Field label={recovery ? "Recovery code" : "6-digit code"}>
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
          Verify
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
          {recovery ? "Use the authenticator code" : "Use a recovery code"}
        </Button>
        {pending && (
          <Button variant="link" onClick={onStartOver}>
            Start setup again
          </Button>
        )}
      </div>
    </MfaPage>
  );
}
