import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "../lib/cn";
import { Spinner } from "./Spinner";

export const buttonVariants = cva(
  "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-control text-body font-medium transition-colors " +
    "outline-focus focus-visible:outline-2 focus-visible:outline-offset-2 disabled:pointer-events-none disabled:opacity-50 max-sm:min-h-11",
  {
    variants: {
      variant: {
        default: "bg-action text-on-action hover:bg-action-hover",
        secondary: "bg-action-soft text-on-action-soft hover:bg-subtle",
        outline: "border border-line-strong bg-surface text-fg hover:bg-subtle",
        ghost: "text-fg hover:bg-subtle",
        destructive: "bg-danger text-on-danger hover:bg-danger-hover",
        link: "min-h-10 px-1 text-on-action-soft underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-10 px-3 text-caption",
        md: "h-10 px-4",
        lg: "h-12 px-6 text-card",
        icon: "size-10 p-0",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export interface ButtonProps extends ComponentProps<"button">, VariantProps<typeof buttonVariants> {
  /** Shows a spinner, sets aria-busy and ignores clicks while work is in flight. */
  loading?: boolean;
  /** Render the child element (a link) with the button styling instead of a <button>. */
  asChild?: boolean;
}

export function Button({ className, variant, size, loading = false, asChild = false, disabled, children, type = "button", ...props }: ButtonProps) {
  const classes = cn(buttonVariants({ variant, size }), className);
  if (asChild) return <Slot className={classes} {...props}>{children}</Slot>;
  return (
    <button type={type} className={classes} disabled={disabled || loading} aria-busy={loading || undefined} {...props}>
      {loading && <Spinner />}
      {children}
    </button>
  );
}