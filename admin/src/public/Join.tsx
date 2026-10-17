import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { Trans, useTranslation } from "react-i18next";
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
import { MIN_PASSWORD, PasswordForm } from "./PasswordForm";
import { PublicFrame } from "./PublicFrame";
import { usePublicBranding } from "./usePublicBranding";

/** Who the invitation is for: not known yet, known from the server's preview, to be asked for (older server or a slow answer), or the uniform 404. */
type Who = { status: "loading" | "asking" | "unusable" } | { status: "known"; email: string };
const PREVIEW_WAIT_MS = 3000;

const MESSAGE_KEYS = { throttled: "join.throttled", unavailable: "join.unavailable", offline: "join.offline" } as const;

/**
 * The page the invitation email lands on: `/admin/join?c=<company code>#invitation_id=…&capability=…`. Signed-out and unauthenticated by
 * design. The capability is read once into memory and removed from the address bar; branding for the company code is resolved before the
 * form shows; accepting sets the password, signs in and leads to the download page.
 */
export function Join() {
  const { t } = useTranslation("public");
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
      <main role="status" aria-label={t("join.loading")} className="mx-auto flex min-h-screen w-full max-w-lg flex-col justify-center gap-6 p-4 sm:p-6">
        <Skeleton className="h-12 w-48" />
        <Skeleton className="h-72 w-full" />
      </main>
    );
  }
  if (token) {
    return (
      <PublicFrame brand={theme} title={t("join.signedInTitle")} description={t("join.signedInDescription")}>
        <div className="flex flex-wrap gap-3">
          <Button variant="outline" onClick={() => void signOut(services)}>{t("join.signOutFirst")}</Button>
          <Button onClick={() => navigate("/", { replace: true })}>{t("join.continueHome")}</Button>
        </div>
      </PublicFrame>
    );
  }
  if (!link) {
    return (
      <PublicFrame brand={theme} title={t("join.incompleteTitle")} description={t("join.incompleteDescription")}>
        <Button variant="outline" onClick={() => navigate("/", { replace: true })}>{t("join.goToSignIn")}</Button>
      </PublicFrame>
    );
  }
  if (failure === "invalid") {
    return (
      <PublicFrame brand={theme} title={t("join.invalidTitle")} description={t("join.invalidDescription")}>
        <Button onClick={() => navigate("/", { replace: true })}>{t("join.goToSignIn")}</Button>
      </PublicFrame>
    );
  }
  if (failure === "existing_account") {
    return (
      <PublicFrame brand={theme} title={t("join.existingTitle")} description={t("join.existingDescription")}>
        <Button onClick={() => navigate("/", { replace: true })}>{t("join.signIn")}</Button>
      </PublicFrame>
    );
  }
  if (ready) {
    return (
      <PublicFrame brand={theme} title={t("join.readyTitle")} description={t("join.readyDescription")}>
        <Button onClick={() => navigate("/", { replace: true })}>{t("join.signIn")}</Button>
      </PublicFrame>
    );
  }

  async function submit(password: string) {
    setFailure(null);
    const typed = who.status === "known" ? who.email : email.trim();
    if (!z.email().safeParse(typed).success) {
      setEmailError(t("validation.invitationEmail"));
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
    <PublicFrame brand={theme} title={t("join.title")} description={loginCopy ?? t("join.welcome", { name: theme.name })}>
      <PasswordForm
        submitLabel={t("join.submit")}
        error={failure === "password" ? t("join.passwordRejected", { min: MIN_PASSWORD }) : failure ? t(MESSAGE_KEYS[failure]) : null}
        onSubmit={submit}
      >
        {who.status === "known" ? (
          <p className="text-body text-fg"><Trans t={t} i18nKey="join.joiningAs" values={{ email: who.email }} components={{ strong: <strong /> }} /></p>
        ) : (
          <Field label={t("join.yourEmail")} hint={t("join.yourEmailHint")} error={emailError ?? undefined}>
            {(control) => <Input {...control} type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} />}
          </Field>
        )}
      </PasswordForm>
      {code && <Alert tone="info"><Trans t={t} i18nKey="join.companyCode" values={{ code }} components={{ strong: <strong /> }} /></Alert>}
    </PublicFrame>
  );
}