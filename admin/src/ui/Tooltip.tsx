import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import type { ReactElement, ReactNode } from "react";

/** Supplementary text only: the trigger must already have an accessible name. Opens on hover and on keyboard focus. */
export function Tooltip({ content, children }: { content: ReactNode; children: ReactElement }) {
  return (
    <TooltipPrimitive.Provider delayDuration={200}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content sideOffset={6} className="z-50 max-w-64 rounded-control bg-nav px-2.5 py-1.5 text-caption text-on-nav shadow-overlay">
            {content}
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}