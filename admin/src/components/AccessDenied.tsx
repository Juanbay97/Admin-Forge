interface AccessDeniedProps {
  title?: string;
  message?: string;
  onSignOut: () => void;
}

export function AccessDenied({
  title = "Access denied",
  message = "This console is for organization administrators.",
  onSignOut,
}: AccessDeniedProps) {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 p-6">
      <h1 className="font-title text-2xl font-bold text-primary">{title}</h1>
      <p>{message}</p>
      <button
        type="button"
        onClick={onSignOut}
        className="self-start rounded bg-teal px-4 py-2 font-medium text-white transition-colors hover:bg-primary"
      >
        Sign out
      </button>
    </main>
  );
}