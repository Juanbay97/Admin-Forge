import { useState } from "react";
import { useNavigate } from "react-router";
import { ApiError } from "../api/client";
import { defaultTheme } from "../brand/theme";
import { Alert } from "../ui/Alert";
import { Button } from "../ui/Button";
import { readCapability, scrubFragment } from "./fragment";
import { PasswordForm } from "./PasswordForm";
import { PublicFrame } from "./PublicFrame";

/**
 * The page the owner set-password link lands on (`/reset-password#capability=…`). The capability is read once into memory and
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

  if (!capability) {
    return (
      <PublicFrame brand={defaultTheme} title="This link cannot be used" description="It is incomplete, expired or was already used. Ask for a new one, or sign in if you already set your password.">
        <Button onClick={() => navigate("/", { replace: true })}>Go to sign in</Button>
      </PublicFrame>
    );
  }
  if (done) {
    return (
      <PublicFrame brand={defaultTheme} title="Password set" description="You can sign in with your new password now.">
        <Alert tone="success" title="All done">
          Your password was saved.
        </Alert>
        <Button size="lg" onClick={() => navigate("/", { replace: true })}>
          Continue to sign in
        </Button>
      </PublicFrame>
    );
  }
  return (
    <PublicFrame brand={defaultTheme} title="Set your password" description="Choose the password you will use to sign in.">
      <PasswordForm
        submitLabel="Set password"
        error={error}
        onSubmit={async (password) => {
          setError(null);
          try {
            await consume(capability, password);
            setDone(true);
          } catch (failure) {
            const status = failure instanceof ApiError ? failure.status : 0;
            setError(status === 404 ? "This link is no longer valid. Ask for a new one." : status === 422 ? "That password is not accepted. Use at least 15 characters." : "Setting the password is unavailable. Try again later.");
          }
        }}
      />
    </PublicFrame>
  );
}
