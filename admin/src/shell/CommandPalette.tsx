import { Command } from "cmdk";
import { Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { Dialog } from "../ui/overlay/Dialog";
import type { NavEntry } from "./areas";
import { NavIcon } from "./icons";

/** Ctrl/Cmd+K: filter the current area's pages, Enter navigates, Escape closes and the browser restores focus. */
/** A destination beyond the area's pages, e.g. one company; `hint` is matched too (the company code). */
export interface PaletteCommand {
  label: string;
  to: string;
  hint?: string;
}

export function CommandPalette({ open, onOpenChange, nav, commands = [] }: { open: boolean; onOpenChange: (open: boolean) => void; nav: NavEntry[]; commands?: PaletteCommand[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={t("shell.commandPalette")} hideTitle className="max-w-lg">
      <Command label={t("shell.pages")} className="flex flex-col gap-2">
        <div className="flex items-center gap-2 rounded-control border border-line-strong px-3">
          <Search aria-hidden="true" className="size-4 text-muted" />
          <Command.Input placeholder={t("shell.goTo")} aria-label={t("shell.searchPages")} className="h-11 w-full bg-transparent text-body text-fg outline-none placeholder:text-muted" />
        </div>
        <Command.List className="max-h-72 overflow-y-auto">
          <Command.Empty className="px-3 py-6 text-center text-body text-muted">{t("shell.noMatchingPage")}</Command.Empty>
          {nav.map((entry) => (
            <Command.Item
              key={entry.to}
              value={t(entry.labelKey)}
              onSelect={() => {
                onOpenChange(false);
                navigate(entry.to);
              }}
              className="flex min-h-11 cursor-pointer items-center gap-3 rounded-control px-3 text-body text-fg data-[selected=true]:bg-subtle"
            >
              <NavIcon name={entry.icon} className="size-4 text-muted" />
              {t(entry.labelKey)}
            </Command.Item>
          ))}
          {commands.length > 0 && (
            <Command.Group heading={t("shell.companies")} className="pt-2 text-caption text-muted">
              {commands.map((command) => (
                <Command.Item
                  key={command.to}
                  value={`${command.label} ${command.hint ?? ""}`}
                  onSelect={() => {
                    onOpenChange(false);
                    navigate(command.to);
                  }}
                  className="flex min-h-11 cursor-pointer items-center gap-3 rounded-control px-3 text-body text-fg data-[selected=true]:bg-subtle"
                >
                  {command.label}
                  {command.hint && <span className="ml-auto text-caption text-muted">{command.hint}</span>}
                </Command.Item>
              ))}
            </Command.Group>
          )}
        </Command.List>
      </Command>
    </Dialog>
  );
}