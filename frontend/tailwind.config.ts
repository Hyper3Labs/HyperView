import type { Config } from "tailwindcss";

export default {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Dark theme colors (shadcn-style with Indigo primary)
        background: "#0a0a0b",
        surface: "#18181b",
        "surface-light": "#27272a",
        border: "#3f3f46",
        primary: "#4F46E5",
        "primary-light": "#818CF8",
        text: "#fafafa",
        "text-muted": "#a1a1aa",
      },
    },
  },
  plugins: [],
} satisfies Config;
