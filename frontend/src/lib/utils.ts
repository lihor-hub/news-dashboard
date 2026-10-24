import { clsx, type ClassValue } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

// Teach tailwind-merge that the custom `text-meta` / `text-reading` utilities
// (globals.css) are font sizes, so they don't evict text colour classes.
const twMerge = extendTailwindMerge({
  extend: { classGroups: { 'font-size': [{ text: ['meta', 'reading'] }] } },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
