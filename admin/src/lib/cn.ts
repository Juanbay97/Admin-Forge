import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * Joins class names and lets the last conflicting Tailwind utility win. The type-scale utilities defined in
 * `brand/tokens.css` (`text-page`, `text-body`, ...) are registered as font sizes so they are never mistaken
 * for text colours and silently dropped next to `text-fg`.
 */
const merge = extendTailwindMerge({
  extend: {
    classGroups: { "font-size": [{ text: ["page", "section", "card", "body", "caption"] }] },
    theme: { radius: ["control", "card"] },
  },
});

export function cn(...inputs: ClassValue[]): string {
  return merge(clsx(inputs));
}