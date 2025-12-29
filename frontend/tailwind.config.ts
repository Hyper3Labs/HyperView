import type { Config } from "tailwindcss";

export default {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./content/**/*.{js,ts,jsx,tsx,mdx}",
    "./node_modules/fumadocs-ui/dist/**/*.js",
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
      typography: {
        DEFAULT: {
          css: {
            maxWidth: 'none',
            color: '#fafafa',
            a: {
              color: '#818CF8',
              '&:hover': {
                color: '#4F46E5',
              },
            },
            h1: {
              color: '#fafafa',
            },
            h2: {
              color: '#fafafa',
            },
            h3: {
              color: '#fafafa',
            },
            h4: {
              color: '#fafafa',
            },
            strong: {
              color: '#fafafa',
            },
            code: {
              color: '#818CF8',
              backgroundColor: '#27272a',
              padding: '0.25rem 0.375rem',
              borderRadius: '0.25rem',
              fontWeight: '400',
            },
            'code::before': {
              content: '""',
            },
            'code::after': {
              content: '""',
            },
            pre: {
              backgroundColor: '#18181b',
              border: '1px solid #3f3f46',
            },
            blockquote: {
              color: '#a1a1aa',
              borderLeftColor: '#4F46E5',
            },
          },
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
} satisfies Config;
