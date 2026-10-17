import { Languages } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "../lib/cn";
import { currentLanguage, LANGUAGES, setLanguage, type Language } from "./config";

/** Each language is named in itself, so it can be found whatever language the page is currently in. */
const NAMES: Record<Language, string> = { en: "English", es: "Español" };

/**
 * The visible language switch. A native <select> keeps platform keyboard and mobile behavior; the choice is applied at once and
 * remembered in localStorage (see `setLanguage`).
 */
export function LanguageSwitch({ className }: { className?: string }) {
  const { t } = useTranslation(); // subscribes to language changes, so the label and the selected option re-render
  const language = currentLanguage();
  return (
    <label className={cn("inline-flex h-10 items-center gap-1.5 rounded-control border border-line-strong bg-surface px-2.5 text-body text-fg outline-focus focus-within:outline-2 max-sm:min-h-11", className)}>
      <Languages aria-hidden="true" className="size-4 text-muted" />
      <select
        aria-label={t("language.label")}
        value={language}
        onChange={(event) => setLanguage(event.target.value as Language)}
        className="cursor-pointer appearance-none bg-transparent pr-1 text-body outline-none"
      >
        {LANGUAGES.map((code) => (
          <option key={code} value={code} lang={code}>
            {NAMES[code]}
          </option>
        ))}
      </select>
    </label>
  );
}
