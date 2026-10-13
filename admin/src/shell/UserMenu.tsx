import { LogOut } from "lucide-react";
import { Button } from "../ui/Button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "../ui/DropdownMenu";
import type { Identity } from "./identity";

const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]!.toUpperCase()).join("") || "?";

/** Who is signed in. Sign out also has its own always-visible button in the topbar. */
export function UserMenu({ identity, onSignOut }: { identity: Identity; onSignOut: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Account menu" className="rounded-full bg-action-soft text-on-action-soft">
          <span aria-hidden="true" className="text-caption font-semibold">{initials(identity.account.display_name)}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <div className="px-3 py-2">
          <p className="text-body font-semibold text-fg">{identity.account.display_name}</p>
          <p className="text-caption text-muted">{identity.account.email}</p>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onSignOut}>
          <LogOut aria-hidden="true" className="size-4" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}