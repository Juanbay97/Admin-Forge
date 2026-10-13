import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, type FieldValues, type UseFormProps, type UseFormReturn } from "react-hook-form";
import type { ZodType } from "zod";
import "../lib/zod";

/** react-hook-form wired to a zod schema; errors surface after a field is touched, then on every change. */
export function useZodForm<T extends FieldValues>(
  schema: ZodType<T, FieldValues>,
  options: Omit<UseFormProps<T>, "resolver"> = {},
): UseFormReturn<T> {
  return useForm<T>({ mode: "onTouched", ...options, resolver: zodResolver(schema as never) as never });
}