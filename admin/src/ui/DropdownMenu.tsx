import * as MenuPrimitive from "@radix-ui/react-dropdown-menu";
import type { ComponentProps } from "react";
import { cn } from "../lib/cn";

/** Non-modal on purpose: the modal variant locks scroll through `react-remove-scroll`, which injects a <style>. */
export function DropdownMenu(props: Omit<ComponentProps<typeof MenuPrimitive.Root>, "modal">) {
  return <MenuPrimitive.Root modal={false} {...props} />;
}

export const DropdownMenuTrigger = MenuPrimitive.Trigger;

export function DropdownMenuContent({ className, ...props }: ComponentProps<typeof MenuPrimitive.Content>) {
  return (
    <MenuPrimitive.Portal>
      <MenuPrimitive.Content
        align="end"
        sideOffset={6}
        className={cn("z-50 min-w-44 rounded-card border border-line bg-raised p-1 text-body text-fg shadow-overlay", className)}
        {...props}
      />
    </MenuPrimitive.Portal>
  );
}

export function DropdownMenuItem({ className, destructive, ...props }: ComponentProps<typeof MenuPrimitive.Item> & { destructive?: boolean }) {
  return (
    <MenuPrimitive.Item
      className={cn(
        "flex min-h-10 cursor-pointer select-none items-center gap-2 rounded-control px-3 outline-none",
        "data-[highlighted]:bg-subtle data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        destructive && "text-on-danger-soft",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuSeparator({ className, ...props }: ComponentProps<typeof MenuPrimitive.Separator>) {
  return <MenuPrimitive.Separator className={cn("my-1 h-px bg-line", className)} {...props} />;
}