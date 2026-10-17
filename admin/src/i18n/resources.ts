import enCommon from "./locales/en/common.json" with { type: "json" };
import enCompany from "./locales/en/company.json" with { type: "json" };
import enLanding from "./locales/en/landing.json" with { type: "json" };
import enPlatform from "./locales/en/platform.json" with { type: "json" };
import enPortal from "./locales/en/portal.json" with { type: "json" };
import enPublic from "./locales/en/public.json" with { type: "json" };
import esCommon from "./locales/es/common.json" with { type: "json" };
import esCompany from "./locales/es/company.json" with { type: "json" };
import esLanding from "./locales/es/landing.json" with { type: "json" };
import esPlatform from "./locales/es/platform.json" with { type: "json" };
import esPortal from "./locales/es/portal.json" with { type: "json" };
import esPublic from "./locales/es/public.json" with { type: "json" };

/** One namespace per area; `common` holds the shell, the shared components and the error copy. */
export const NAMESPACES = ["common", "platform", "company", "portal", "public", "landing"] as const;
export type Namespace = (typeof NAMESPACES)[number];

export const resources = {
  en: { common: enCommon, platform: enPlatform, company: enCompany, portal: enPortal, public: enPublic, landing: enLanding },
  es: { common: esCommon, platform: esPlatform, company: esCompany, portal: esPortal, public: esPublic, landing: esLanding },
} as const;

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "common";
    // English is the source catalogue: every translation key is checked against it at compile time.
    resources: (typeof resources)["en"];
  }
}
