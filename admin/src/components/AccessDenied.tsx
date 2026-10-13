import { ShieldAlert } from "lucide-react";
import { Button } from "../ui/Button";

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
      <span className="flex size-12 items-center justify-center rounded-full bg-danger-soft text-on-danger-soft">
        <ShieldAlert aria-hidden="true" className="size-6" />
      </span>
      <h1 className="font-title text-page font-bold text-fg">{title}</h1>
      <p className="text-body text-muted">{message}</p>
      <Button className="self-start" onClick={onSignOut}>
        Sign out
      </Button>
    </main>
  );
}