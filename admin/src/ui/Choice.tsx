import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import * as RadioGroupPrimitive from "@radix-ui/react-radio-group";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import { Check } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "../lib/cn";

// Each choice renders its own <label> row: the whole row is the 40px-tall target and gives the control its name.
const row = "flex min-h-10 cursor-pointer items-center gap-3 text-body text-fg has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50";
const focus = "outline-focus focus-visible:outline-2 focus-visible:outline-offset-2";

export function Checkbox({ label, className, ...props }: ComponentProps<typeof CheckboxPrimitive.Root> & { label: ReactNode }) {
  return (
    <label className={cn(row, className)}>
      <CheckboxPrimitive.Root
        className={cn(
          "flex size-5 shrink-0 items-center justify-center rounded border border-line-strong bg-surface text-on-action",
          "data-[state=checked]:border-action data-[state=checked]:bg-action",
          focus,
        )}
        {...props}
      >
        <CheckboxPrimitive.Indicator>
          <Check aria-hidden="true" className="size-3.5" strokeWidth={3} />
        </CheckboxPrimitive.Indicator>
      </CheckboxPrimitive.Root>
      {label}
    </label>
  );
}

export function Switch({ label, className, ...props }: ComponentProps<typeof SwitchPrimitive.Root> & { label: ReactNode }) {
  return (
    <label className={cn(row, className)}>
      <SwitchPrimitive.Root
        className={cn("relative h-6 w-11 shrink-0 rounded-full bg-line-strong transition-colors data-[state=checked]:bg-action", focus)}
        {...props}
      >
        <SwitchPrimitive.Thumb className="block size-5 translate-x-0.5 rounded-full bg-surface shadow-card transition-transform data-[state=checked]:translate-x-[22px]" />
      </SwitchPrimitive.Root>
      {label}
    </label>
  );
}

export function RadioGroup({ className, ...props }: ComponentProps<typeof RadioGroupPrimitive.Root>) {
  return <RadioGroupPrimitive.Root className={cn("flex flex-col gap-1", className)} {...props} />;
}

export function Radio({ label, className, ...props }: ComponentProps<typeof RadioGroupPrimitive.Item> & { label: ReactNode }) {
  return (
    <label className={cn(row, className)}>
      <RadioGroupPrimitive.Item
        className={cn(
          "flex size-5 shrink-0 items-center justify-center rounded-full border border-line-strong bg-surface",
          "data-[state=checked]:border-action",
          focus,
        )}
        {...props}
      >
        <RadioGroupPrimitive.Indicator className="size-2.5 rounded-full bg-action" />
      </RadioGroupPrimitive.Item>
      {label}
    </label>
  );
}