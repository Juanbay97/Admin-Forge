import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, type FieldValues, type UseFormProps, type UseFormReturn } from "react-hook-form";
import { config, type ZodType } from "zod";

// zod compiles validators with `new Function` unless told not to; under `script-src 'self'` the probe itself is reported
// as a securitypolicyviolation. Every form goes through this module, so the setting is applied before any schema runs.
config({ jitless: true });

/** react-hook-form wired to a zod schema; errors surface after a field is touched, then on every change. */
export function useZodForm<T extends FieldValues>(
  schema: ZodType<T, FieldValues>,
  options: Omit<UseFormProps<T>, "resolver"> = {},
): UseFormReturn<T> {
  return useForm<T>({ mode: "onTouched", ...options, resolver: zodResolver(schema as never) as never });
}