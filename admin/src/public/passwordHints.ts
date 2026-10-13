import { MIN_PASSWORD } from "./passwordRules";

export function passwordHints(value: string): { longEnough: boolean; remaining: number } {
  const length = [...value].length;
  return { longEnough: length >= MIN_PASSWORD, remaining: Math.max(0, MIN_PASSWORD - length) };
}