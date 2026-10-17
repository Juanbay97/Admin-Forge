import { issue, t } from "../../../../i18n/config";
import { z } from "../../../../lib/zod";
import { isCompanyCode } from "../../../../platform/companies";

type FieldName = "companyName" | "department" | "adminName";
const text = (field: FieldName, max: number) =>
  z
    .string()
    .trim()
    .min(1, issue("platform:wizard.errors.required", () => ({ what: t(`platform:wizard.fields.${field}`) })))
    .max(max, issue("platform:wizard.errors.max", { max }));

export const companySchema = z.object({
  name: text("companyName", 120),
  code: z.string().refine(isCompanyCode, issue("platform:wizard.errors.code")),
  department: text("department", 120),
});

export const adminSchema = z.object({
  email: z.string().trim().min(1, issue("platform:wizard.errors.email")).pipe(z.email(issue("public:validation.emailInvalid")).max(254)),
  name: text("adminName", 120),
});

export const keysSchema = z.object({
  keys: z.array(z.string().uuid()).min(1, issue("platform:wizard.errors.keysMin")).max(16, issue("platform:wizard.errors.keysMax")),
});

export type CompanyStep = z.infer<typeof companySchema>;
export type AdminStep = z.infer<typeof adminSchema>;
export type KeysStep = z.infer<typeof keysSchema>;