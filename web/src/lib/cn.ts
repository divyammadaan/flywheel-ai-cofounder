import { type ClassValue, clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * Merge class names, with later Tailwind utilities winning over earlier ones.
 *
 * tailwind-merge has to be told about this project's tokens. Out of the box it
 * sees `text-display` and `text-pivot` as the same `text-*` group and drops the
 * first -- which silently rendered the verdict, the page's largest and most
 * consequential element, at body size. Custom scales are declared here so a
 * size and a colour can coexist on one element.
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        { text: ["display", "title", "heading", "body", "small", "caption"] },
      ],
      "text-color": [
        {
          text: [
            "ink",
            "ink-muted",
            "ink-faint",
            "accent",
            "go",
            "pivot",
            "nogo",
            "warning",
          ],
        },
      ],
    },
  },
});

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
