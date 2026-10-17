import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, type ButtonProps } from "./Button";

interface CopyButtonProps extends Omit<ButtonProps, "onClick" | "children"> {
  value: string;
  label?: string;
  copiedLabel?: string;
}

/** Copies a non-secret value and says so, for sighted users and through a polite status for screen readers. */
export function CopyButton({ value, label, copiedLabel, variant = "outline", size = "sm", ...props }: CopyButtonProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(timer);
  }, [copied]);
  return (
    <>
      <Button
        variant={variant}
        size={size}
        onClick={() => void navigator.clipboard.writeText(value).then(() => setCopied(true), () => setCopied(false))}
        {...props}
      >
        {copied ? <Check aria-hidden="true" className="size-4" /> : <Copy aria-hidden="true" className="size-4" />}
        {copied ? (copiedLabel ?? t("ui.copy.copied")) : (label ?? t("ui.copy.copy"))}
      </Button>
      <span role="status" className="sr-only">{copied ? t("ui.copy.copiedToClipboard") : ""}</span>
    </>
  );
}