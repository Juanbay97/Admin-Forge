// Test-build only (see `main.tsx`): mounts every allow-listed third-party primitive so the UI suite can drive it
// under the production CSP. Anything that creates a <style> element fails `tests/ui/primitives-csp.spec.ts`.
import * as Checkbox from "@radix-ui/react-checkbox";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import * as Label from "@radix-ui/react-label";
import * as Popover from "@radix-ui/react-popover";
import * as RadioGroup from "@radix-ui/react-radio-group";
import { Slot } from "@radix-ui/react-slot";
import * as Switch from "@radix-ui/react-switch";
import * as Tabs from "@radix-ui/react-tabs";
import * as Tooltip from "@radix-ui/react-tooltip";
import { Command } from "cmdk";
import { Check, Search } from "lucide-react";

export function PrimitiveSpike() {
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 p-6 text-body">
      <h1 className="font-title text-page">Primitive spike</h1>

      <Tabs.Root defaultValue="overview">
        <Tabs.List aria-label="Sections" className="flex gap-2">
          <Tabs.Trigger value="overview">Overview</Tabs.Trigger>
          <Tabs.Trigger value="usage">Usage</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="overview">Overview panel</Tabs.Content>
        <Tabs.Content value="usage">Usage panel</Tabs.Content>
      </Tabs.Root>

      <div className="flex flex-wrap items-center gap-3">
        <Tooltip.Provider delayDuration={0}>
          <Tooltip.Root>
            <Tooltip.Trigger asChild>
              <button type="button">Tooltip trigger</button>
            </Tooltip.Trigger>
            <Tooltip.Portal>
              <Tooltip.Content sideOffset={6}>Copies the value</Tooltip.Content>
            </Tooltip.Portal>
          </Tooltip.Root>
        </Tooltip.Provider>

        <Popover.Root>
          <Popover.Trigger asChild>
            <button type="button">Popover trigger</button>
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content sideOffset={6}>Popover body</Popover.Content>
          </Popover.Portal>
        </Popover.Root>

        <DropdownMenu.Root modal={false}>
          <DropdownMenu.Trigger asChild>
            <button type="button">Menu trigger</button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content sideOffset={6}>
              <DropdownMenu.Item>Rename</DropdownMenu.Item>
              <DropdownMenu.Item>Archive</DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Switch.Root id="spike-notifications" className="h-6 w-11 rounded-full border">
            <Switch.Thumb />
          </Switch.Root>
          <Label.Root htmlFor="spike-notifications">Notifications</Label.Root>
        </div>
        <div className="flex items-center gap-2">
          <Checkbox.Root id="spike-terms" className="size-5 rounded border">
            <Checkbox.Indicator>
              <Check aria-hidden="true" size={14} />
            </Checkbox.Indicator>
          </Checkbox.Root>
          <Label.Root htmlFor="spike-terms">Accept terms</Label.Root>
        </div>
        <RadioGroup.Root aria-label="Cadence" defaultValue="weekly" className="flex gap-4">
          <div className="flex items-center gap-2">
            <RadioGroup.Item value="weekly" id="spike-weekly" className="size-5 rounded-full border">
              <RadioGroup.Indicator />
            </RadioGroup.Item>
            <Label.Root htmlFor="spike-weekly">Weekly</Label.Root>
          </div>
          <div className="flex items-center gap-2">
            <RadioGroup.Item value="monthly" id="spike-monthly" className="size-5 rounded-full border">
              <RadioGroup.Indicator />
            </RadioGroup.Item>
            <Label.Root htmlFor="spike-monthly">Monthly</Label.Root>
          </div>
        </RadioGroup.Root>
      </div>

      <Search aria-hidden="true" size={16} />
      <Slot className="underline">
        <a href="#slot">Slot link</a>
      </Slot>

      <Command label="Commands">
        <Command.Input placeholder="Search commands" />
        <Command.List>
          <Command.Item>Members</Command.Item>
          <Command.Item>Gateway</Command.Item>
        </Command.List>
      </Command>
    </main>
  );
}
