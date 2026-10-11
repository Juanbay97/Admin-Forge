import { useState, type FormEvent } from "react";
import type { AccountApi } from "../api/account";
import { ApiError } from "../api/client";
import { defaultTheme } from "../brand/theme";

const MESSAGES: Record<number, string> = {
  401: "Email or password is incorrect.",
  429: "Too many sign-in attempts. Try again later.",
};

interface LoginProps {
  api: AccountApi;
  onSignedIn: (token: string) => void;
}

export function Login({ api, onSignedIn }: LoginProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const attempt = password;
    setPassword(""); // the secret never outlives the submit, successful or not
    try {
      onSignedIn(await api.login(email, attempt));
    } catch (failure) {
      const status = failure instanceof ApiError ? failure.status : 0;
      setError(MESSAGES[status] ?? "Sign-in is unavailable. Try again later.");
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-6">
      <header className="flex items-center gap-4">
        <img src={defaultTheme.assets.markOnLight} alt="" className="h-14 w-auto" />
        <div>
          <h1 className="font-title text-2xl font-bold text-primary">{defaultTheme.name}</h1>
          <p className="text-sm">Administration</p>
        </div>
      </header>
      <form onSubmit={submit} className="flex flex-col gap-4 rounded-lg bg-white p-6 shadow">
        <label className="flex flex-col gap-1 text-sm font-medium">
          Email
          <input
            type="email"
            autoComplete="username"
            required
            autoFocus
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="rounded border border-carbon/40 px-3 py-2 text-base"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="rounded border border-carbon/40 px-3 py-2 text-base"
          />
        </label>
        {error && (
          <p role="alert" className="text-sm font-medium text-red-800">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-teal px-4 py-2 font-medium text-white transition-colors hover:bg-primary disabled:opacity-60"
        >
          Sign in
        </button>
      </form>
    </main>
  );
}