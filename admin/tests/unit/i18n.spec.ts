import { expect, test } from "@playwright/test";
import { currentLanguage, detectLanguage, i18n, LANGUAGE_STORAGE_KEY, languageFromBrowser, languageOf, setLanguage, t } from "../../src/i18n/config";
import { NAMESPACES, resources } from "../../src/i18n/resources";
import { formatCostMicros, formatDate, formatDateTime, formatNumber, formatPercent, formatTokens } from "../../src/lib/format";
import { formatTick, timeTicks } from "../../src/charts/ticks";

type Tree = { [key: string]: string | Tree };

/** Every leaf as a dotted path, in catalogue order. */
function leaves(tree: Tree, prefix = ""): Array<[string, string]> {
  return Object.entries(tree).flatMap(([key, value]) => (typeof value === "string" ? [[`${prefix}${key}`, value] as [string, string]] : leaves(value, `${prefix}${key}.`)));
}

/** `{{name}}` placeholders and `<tag>` markers of a message, sorted. */
const markers = (message: string): string[] => [...(message.match(/\{\{[^}]+\}\}|<\/?[a-z0-9]+>/gi) ?? [])].sort();

test.describe("catalogue parity", () => {
  for (const namespace of NAMESPACES) {
    test(`${namespace}: es has exactly the keys of en, in the same order`, () => {
      const en = leaves(resources.en[namespace] as Tree).map(([path]) => path);
      const es = leaves(resources.es[namespace] as Tree).map(([path]) => path);
      expect(es).toEqual(en);
    });

    test(`${namespace}: every message has the same placeholders in both languages and none is empty`, () => {
      const es = new Map(leaves(resources.es[namespace] as Tree));
      for (const [path, english] of leaves(resources.en[namespace] as Tree)) {
        const spanish = es.get(path);
        expect(english.trim(), `en ${namespace}:${path} is empty`).not.toBe("");
        expect(spanish?.trim(), `es ${namespace}:${path} is empty`).not.toBe("");
        expect(markers(spanish ?? ""), `placeholders of ${namespace}:${path}`).toEqual(markers(english));
      }
    });
  }

  test("plural forms come in pairs", () => {
    for (const language of ["en", "es"] as const) {
      for (const namespace of NAMESPACES) {
        const paths = leaves(resources[language][namespace] as Tree).map(([path]) => path);
        for (const path of paths.filter((candidate) => candidate.endsWith("_one"))) expect(paths, `${language} ${namespace}:${path}`).toContain(path.replace(/_one$/, "_other"));
      }
    }
  });
});

test.describe("language detection", () => {
  test("any Spanish tag is Spanish and anything else is English", () => {
    expect(languageOf("es")).toBe("es");
    expect(languageOf("es-CO")).toBe("es");
    expect(languageOf("ES_mx")).toBe("es");
    expect(languageOf("en-US")).toBe("en");
    expect(languageOf("fr-FR")).toBe("en");
    expect(languageOf("")).toBeNull();
    expect(languageOf(undefined)).toBeNull();
  });

  test("the first browser language decides", () => {
    expect(languageFromBrowser(["es-419", "en"])).toBe("es");
    expect(languageFromBrowser(["fr-FR", "es"])).toBe("en");
    expect(languageFromBrowser(["en-GB", "es"])).toBe("en");
    expect(languageFromBrowser([])).toBe("en");
    expect(languageFromBrowser(undefined)).toBe("en");
  });

  test("outside a browser the language is English whatever the machine's locale is", () => {
    expect(detectLanguage()).toBe("en");
    expect(currentLanguage()).toBe("en");
  });

  test("in a page the stored choice beats the browser language", () => {
    const store = new Map<string, string>();
    const page = { navigator: { languages: ["es-CO", "en"], language: "es-CO" }, localStorage: { getItem: (key: string) => store.get(key) ?? null, setItem: (key: string, value: string) => void store.set(key, value) } };
    Object.defineProperty(globalThis, "window", { value: page, configurable: true });
    try {
      expect(detectLanguage()).toBe("es");
      store.set(LANGUAGE_STORAGE_KEY, "en");
      expect(detectLanguage()).toBe("en");
      store.set(LANGUAGE_STORAGE_KEY, "fr");
      expect(detectLanguage()).toBe("es"); // an unknown stored value is ignored
    } finally {
      Reflect.deleteProperty(globalThis, "window");
    }
  });
});

test.describe("the active language drives copy and formatting", () => {
  test.afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  test("setLanguage switches catalogue, stores the choice and tolerates unavailable storage", async () => {
    const store = new Map<string, string>();
    const storage = { getItem: (key: string) => store.get(key) ?? null, setItem: (key: string, value: string) => void store.set(key, value) };
    Object.defineProperty(globalThis, "window", { value: { navigator: { languages: ["en"] }, localStorage: storage }, configurable: true });
    try {
      setLanguage("es");
      expect(currentLanguage()).toBe("es");
      expect(t("shell.signOut")).toBe("Cerrar sesión");
      expect(store.get(LANGUAGE_STORAGE_KEY)).toBe("es");
      expect(detectLanguage()).toBe("es");
      Object.defineProperty(globalThis, "window", { value: { navigator: { languages: ["es"] }, get localStorage(): never { throw new Error("blocked"); } }, configurable: true });
      setLanguage("en");
      expect(t("shell.signOut")).toBe("Sign out");
      expect(detectLanguage()).toBe("es"); // storage is blocked: the browser language decides
    } finally {
      Reflect.deleteProperty(globalThis, "window");
    }
  });

  test("plurals follow each language's rules", async () => {
    expect(t("ui.pagination.results", { count: 1 })).toBe("1 result");
    expect(t("ui.pagination.results", { count: 2 })).toBe("2 results");
    await i18n.changeLanguage("es");
    expect(t("ui.pagination.results", { count: 1 })).toBe("1 resultado");
    expect(t("ui.pagination.results", { count: 2 })).toBe("2 resultados");
    expect(t("ui.pagination.results", { count: 1_000_000 })).toBe("1000000 resultados");
  });

  test("numbers, currency, percentages and dates use the active locale", async () => {
    expect(formatNumber(1234567.5)).toBe("1,234,567.5");
    expect(formatCostMicros(1_234_560_000)).toBe("$1,234.56");
    expect(formatTokens(1_234_567)).toBe("1.2M");
    expect(formatPercent(0.256, 1)).toBe("25.6%");
    expect(formatDate("2026-10-12T23:30:00Z")).toBe("Oct 12, 2026");
    expect(formatTick(Date.UTC(2026, 9, 1))).toBe("Oct 1");
    await i18n.changeLanguage("es");
    expect(formatNumber(1234567.5)).toBe("1.234.567,5");
    expect(formatCostMicros(4_200)).toMatch(/^0,0042\sUS\$$/);
    expect(formatTokens(1_234_567)).toBe("1,2M");
    expect(formatPercent(0.256, 1)).toMatch(/^25,6\s%$/);
    expect(formatDate("2026-10-12T23:30:00Z")).toMatch(/^12 oct\.? 2026$/);
    expect(formatDateTime("2026-10-12T23:30:00Z")).toMatch(/23:30 UTC$/);
    expect(timeTicks(Date.UTC(2026, 9, 1), Date.UTC(2026, 9, 3), 8).map((tick) => tick.label)).toEqual(["1 oct", "2 oct", "3 oct"]);
    expect(formatNumber(Number.NaN)).toBe("—");
  });

  test("the document language follows the active language", async () => {
    const root = { lang: "" };
    Object.defineProperty(globalThis, "document", { value: { documentElement: root }, configurable: true });
    try {
      await i18n.changeLanguage("es");
      expect(root.lang).toBe("es");
      await i18n.changeLanguage("en");
      expect(root.lang).toBe("en");
    } finally {
      Reflect.deleteProperty(globalThis, "document");
    }
  });
});
