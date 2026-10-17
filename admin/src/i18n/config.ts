import i18n, { type ParseKeys, type TOptions } from "i18next";
import { initReactI18next } from "react-i18next";
import { NAMESPACES, resources, type Namespace } from "./resources";

// The admin ships in English and Spanish. The language follows the browser until the signed-in person picks one in the
// language switch; that choice is stored in localStorage. Every catalogue is bundled (they are small), so there is no network
// round trip and the first paint is already translated.

export const LANGUAGES = ["en", "es"] as const;
export type Language = (typeof LANGUAGES)[number];
export const FALLBACK_LANGUAGE: Language = "en";
export const LANGUAGE_STORAGE_KEY = "forge.admin.language";

const isLanguage = (value: unknown): value is Language => typeof value === "string" && (LANGUAGES as readonly string[]).includes(value);

/** "es", "es-CO" and "ES_mx" are Spanish; anything else, including nothing, is English. */
export function languageOf(tag: string | null | undefined): Language | null {
  if (!tag) return null;
  const primary = tag.trim().toLowerCase().split(/[-_]/)[0];
  return primary === "es" ? "es" : primary ? "en" : null;
}

/** The first browser language wins, so `["fr-FR", "es"]` is English and `["es-AR", "en"]` is Spanish. */
export function languageFromBrowser(languages: readonly string[] | undefined): Language {
  return languageOf(languages?.find((tag) => languageOf(tag))) ?? FALLBACK_LANGUAGE;
}

// Only a real page has a person's language to follow: outside a browser (unit tests, tooling) the language is always English,
// so results never depend on the machine's own locale.
function storage(): Pick<Storage, "getItem" | "setItem"> | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.localStorage;
  } catch {
    return undefined; // private windows and blocked site data can make the accessor throw
  }
}

function readStored(): Language | null {
  try {
    const value = storage()?.getItem(LANGUAGE_STORAGE_KEY);
    return isLanguage(value) ? value : null;
  } catch {
    return null;
  }
}

/** The stored choice, otherwise the browser's language. */
export function detectLanguage(): Language {
  if (typeof window === "undefined") return FALLBACK_LANGUAGE;
  const nav = window.navigator;
  return readStored() ?? languageFromBrowser(nav.languages?.length ? nav.languages : nav.language ? [nav.language] : undefined);
}

function reflect(language: string): void {
  if (typeof document !== "undefined") document.documentElement.lang = language;
}

void i18n.use(initReactI18next).init({
  resources,
  lng: detectLanguage(),
  fallbackLng: FALLBACK_LANGUAGE,
  supportedLngs: [...LANGUAGES],
  ns: [...NAMESPACES],
  defaultNS: "common",
  interpolation: { escapeValue: false }, // React escapes; copy is never injected as HTML
  initAsync: false,
  react: { useSuspense: false },
});
// Both languages carry two plural forms (`_one`, `_other`). CLDR gives Spanish a third category ("many", for 1,000,000 and up) that
// would not resolve to any key, so cardinal selection is limited to the two forms the catalogues have.
const resolver = i18n.services.pluralResolver;
const cardinal = { select: (count: number) => (count === 1 ? "one" : "other"), resolvedOptions: () => ({ pluralCategories: ["one", "other"] }) };
const defaultRule = resolver.getRule.bind(resolver);
resolver.getRule = (code: string, options?: { ordinal?: boolean }) => (options?.ordinal ? defaultRule(code, options) : (cardinal as unknown as Intl.PluralRules));
reflect(i18n.language);
i18n.on("languageChanged", reflect);

export { i18n };
export const t = i18n.t.bind(i18n);

export function currentLanguage(): Language {
  return isLanguage(i18n.language) ? i18n.language : FALLBACK_LANGUAGE;
}

/** Applies and remembers the person's choice. */
export function setLanguage(language: Language): void {
  try {
    storage()?.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    /* the choice still applies to this page view */
  }
  void i18n.changeLanguage(language);
}

/** A zod issue message that is resolved when the issue is raised, so a schema built once still speaks the current language. */
export const issue = (key: ParseKeys<readonly Namespace[]>, options?: TOptions | (() => TOptions)) => ({
  error: () => String(i18n.t(key as never, (typeof options === "function" ? options() : options) as never)),
});

/** BCP 47 tag handed to `Intl`: dates, numbers and currency follow the active language. */
export const localeOf = (language: Language = currentLanguage()): string => language;
