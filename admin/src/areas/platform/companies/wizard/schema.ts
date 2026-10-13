import { z } from "../../../../lib/zod";
import { isCompanyCode } from "../../../../platform/companies";

const text = (label: string, max: number) => z.string().trim().min(1, `Enter ${label}.`).max(max, `Use at most ${max} characters.`);

export const companySchema = z.object({
  name: text("the company name", 120),
  code: z.string().refine(isCompanyCode, "Use 3 to 32 lowercase letters, digits or hyphens, starting with a letter or digit."),
  department: text("the first department", 120),
});

export const adminSchema = z.object({
  email: z.string().trim().min(1, "Enter the email address.").pipe(z.email("Enter a valid email address.").max(254)),
  name: text("the administrator's name", 120),
});

export const keysModelsSchema = z.object({
  keys: z.array(z.string().uuid()).min(1, "Select at least one gateway key.").max(16, "A company can have at most 16 keys."),
  models: z.array(z.string().min(1).max(255)).min(1, "Allow at least one model.").max(500),
});

export type CompanyStep = z.infer<typeof companySchema>;
export type AdminStep = z.infer<typeof adminSchema>;
export type KeysModelsStep = z.infer<typeof keysModelsSchema>;