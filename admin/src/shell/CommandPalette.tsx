import { Command } from "cmdk";
import { Search } from "lucide-react";
import { useNavigate } from "react-router";
import { Dialog } from "../ui/overlay/Dialog";
import type { NavEntry } from "./areas";
import { NavIcon } from "./icons";

/** Ctrl/Cmd+K: filter the current area's pages, Enter navigates, Escape closes and the browser restores focus. */
export function CommandPalette({ open, onOpenChange, nav }: { open: boolean; onOpenChange: (open: boolean) => void; nav: NavEntry[] }) {
  const navigate = useNavigate();
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Command palette" hideTitle className="max-w-lg">
      <Command label="Pages" className="flex flex-col gap-2">
        <div className="flex items-center gap-2 rounded-control border border-line-strong px-3">
          <Search aria-hidden="true" className="size-4 text-muted" />
          <Command.Input placeholder="Go to…" aria-label="Search pages" className="h-11 w-full bg-transparent text-body text-fg outline-none placeholder:text-muted" />
        </div>
        <Command.List className="max-h-72 overflow-y-auto">
          <Command.Empty className="px-3 py-6 text-center text-body text-muted">No matching page.</Command.Empty>
          {nav.map((entry) => (
            <Command.Item
              key={entry.to}
              value={entry.label}
              onSelect={() => {
                onOpenChange(false);
                navigate(entry.to);
              }}
              className="flex min-h-11 cursor-pointer items-center gap-3 rounded-control px-3 text-body text-fg data-[selected=true]:bg-subtle"
            >
              <NavIcon name={entry.icon} className="size-4 text-muted" />
              {entry.label}
            </Command.Item>
          ))}
        </Command.List>
      </Command>
    </Dialog>
  );
}