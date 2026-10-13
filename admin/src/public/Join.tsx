import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { applyBrandIdentity, applyBrandTheme, defaultTheme, themeFromBranding, type BrandTheme } from "../brand/theme";
import { session } from "../auth/session";
import { z } from "../lib/zod";
import { useServices } from "../shell/services";
import { hint, signOut } from "../shell/session";
import { Alert } from "../ui/Alert";
import { Button } from "../ui/Button";
import { Field } from "../ui/Field";
import { Input } from "../ui/Input";
import { Skeleton } from "../ui/Skeleton";
import { readInvitation, scrubFragment } from "./fragment";
import { joinStateFor, type JoinFailure } from "./joinState";
import { PasswordForm } from "./PasswordForm";
import { PublicFrame } from "./PublicFrame";
import { usePublicBranding } from "./usePublicBranding";

/** Who the invitation is for: not known yet, known from the server's preview, to be asked for (older server or a slow answer), or the uniform 404. */
type Who = { status: "loading" | "asking" | "unusable" } | { status: "known"; email: string };
const PREVIEW_WAIT_MS = 3000;

const MESSAGES: Record<"throttled" | "unavailable" | "offline", string> = {
  throttled: "Too many attempts. Wait a few minutes and try again.",
  unavailable: "Joining is unavailable right now. Try again in a moment.",
  offline: "The server could not be reached. Check your connection and try again.",
};

/**
 * The page the invitation email lands on: `/admin/join?c=<company code>#invitation_id=…&capability=…`. Signed-out and unauthenticated by
 * design. The capability is read once into memory and removed from the address bar; branding for the company code is resolved before the
 * form shows; accepting sets the password, signs in and leads to the download page.
 */
export function Join() {
  const services = useServices();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const code = params.get("c");
  const [link] = useState(() => {
    const found = readInvitation(window.location.hash);
    scrubFragment(window.history, window.location);
    return found;
  });
  const token = useSyncExternalStore(session.subscribe, session.token);
  const brand = usePublicBranding(services.branding, code);
  const theme: BrandTheme = useMemo(() => (brand.status === "branded" ? themeFromBranding(brand.branding) : defaultTheme), [brand]);
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState<string | null>(null);
  const [failureState, setFailure] = useState<JoinFailure | null>(null);
  const [ready, setReady] = useState(false);
  const [who, setWho] = useState<Who>({ status: link ? "loading" : "asking" });
  // The server's uniform 404 is shown before anything is typed, in one generic message.
  const failure: JoinFailure | null = failureState ?? (who.status === "unusable" ? "invalid" : null);

  useEffect(() => {
    if (!link) return;
    let current = true;
    const timer = window.setTimeout(() => current && setWho((state) => (state.status === "loading" ? { status: "asking" } : state)), PREVIEW_WAIT_MS);
    services.invitations.preview({ invitationId: link.invitationId, capability: link.capability }).then(
      (found) => current && setWho(found.kind === "known" ? { status: "known", email: found.email } : found.kind === "unusable" ? { status: "unusable" } : { status: "asking" }),
      () => current && setWho({ status: "asking" }), // an outage or a slow answer: ask for the email as before
    );
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [services, link]);

  useEffect(() => {
    if (brand.status === "loading") return;
    applyBrandTheme(theme);
    applyBrandIdentity(theme);
  }, [brand.status, theme]);
  useEffect(
    () => () => {
      applyBrandTheme(defaultTheme);
      applyBrandIdentity(defaultTheme);
    },
    [],
  );

  const loginCopy = brand.status === "branded" ? brand.branding.loginCopy : undefined;

  if (brand.status === "loading" || who.status === "loading") {
    return (
      <main role="status" aria-label="Loading your invitation" className="mx-auto flex min-h-screen w-full max-w-lg flex-col justify-center gap-6 p-4 sm:p-6">
        <Skeleton className="h-12 w-48" />
        <Skeleton className="h-72 w-full" />
      </main>
    );
  }
  if (token) {
    return (
      <PublicFrame brand={theme} title="You are already signed in" description="Accept this invitation from a signed-out browser, or continue to your own home.">
        <div className="flex flex-wrap gap-3">
          <Button variant="outline" onClick={() => void signOut(services)}>Sign out first</Button>
          <Button onClick={() => navigate("/", { replace: true })}>Continue to my home</Button>
        </div>
      </PublicFrame>
    );
  }
  if (!link) {
    return (
      <PublicFrame brand={theme} title="This invitation link is incomplete" description="Open the link from your invitation email exactly as it was sent. If it still does not work, ask your company administrator to invite you again.">
        <Button variant="outline" onClick={() => navigate("/", { replace: true })}>Go to sign in</Button>
      </PublicFrame>
    );
  }
  if (failure === "invalid") {
    return (
      <PublicFrame brand={theme} title="This invitation can no longer be used" description="It may have expired, been used already or been withdrawn, or the link may be wrong. Ask your company administrator for a new invitation. If you already set a password, sign in.">
        <Button onClick={() => navigate("/", { replace: true })}>Go to sign in</Button>
      </PublicFrame>
    );
  }
  if (failure === "existing_account") {
    return (
      <PublicFrame brand={theme} title="You already have a Forge account" description="This invitation is for an email that already has an account. Sign in with it. Joining a second company with the same account is not supported yet.">
        <Button onClick={() => navigate("/", { replace: true })}>Sign in</Button>
      </PublicFrame>
    );
  }
  if (ready) {
    return (
      <PublicFrame brand={theme} title="Your account is ready" description="Sign in with your email and the password you just chose.">
        <Button onClick={() => navigate("/", { replace: true })}>Sign in</Button>
      </PublicFrame>
    );
  }

  async function submit(password: string) {
    setFailure(null);
    const typed = who.status === "known" ? who.email : email.trim();
    if (!z.email().safeParse(typed).success) {
      setEmailError("Enter the email address this invitation was sent to.");
      return;
    }
    setEmailError(null);
    try {
      await services.invitations.accept({ invitationId: link!.invitationId, capability: link!.capability, password });
    } catch (error) {
      setFailure(joinStateFor(error));
      return;
    }
    try {
      const accessToken = await services.account.login(typed, password);
      hint.email = typed;
      session.set(accessToken);
      navigate("/portal/download", { replace: true });
    } catch {
      setReady(true); // the account exists; only the automatic sign-in failed
    }
  }

  return (
    <PublicFrame brand={theme} title="Create your password" description={loginCopy ?? `Welcome to ${theme.name}. Choose the password you will use to sign in.`}>
      <PasswordForm
        submitLabel="Create password and continue"
        error={failure === "password" ? "That password is not accepted. Use at least 15 characters." : failure ? MESSAGES[failure] : null}
        onSubmit={submit}
      >
        {who.status === "known" ? (
          <p className="text-body text-fg">You are joining as <strong>{who.email}</strong>.</p>
        ) : (
          <Field label="Your email" hint="The address this invitation was sent to." error={emailError ?? undefined}>
            {(control) => <Input {...control} type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} />}
          </Field>
        )}
      </PasswordForm>
      {code && <Alert tone="info">Your company code is <strong>{code}</strong>. You will need it in the desktop app.</Alert>}
    </PublicFrame>
  );
}