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
            lineHeight: '1.75',
            fontSize: '1rem',
            p: {
              marginTop: '1.5em',
              marginBottom: '1.5em',
              lineHeight: '1.75',
            },
            a: {
              color: '#818CF8',
              textDecoration: 'none',
              fontWeight: '500',
              '&:hover': {
                color: '#4F46E5',
                textDecoration: 'underline',
              },
            },
            h1: {
              color: '#fafafa',
              fontWeight: '800',
              fontSize: '2.5em',
              marginTop: '0',
              marginBottom: '0.8em',
              lineHeight: '1.2',
            },
            h2: {
              color: '#fafafa',
              fontWeight: '700',
              fontSize: '1.875em',
              marginTop: '2em',
              marginBottom: '1em',
              lineHeight: '1.3',
              paddingBottom: '0.3em',
              borderBottom: '1px solid #3f3f46',
            },
            h3: {
              color: '#fafafa',
              fontWeight: '600',
              fontSize: '1.5em',
              marginTop: '1.6em',
              marginBottom: '0.6em',
              lineHeight: '1.4',
            },
            h4: {
              color: '#fafafa',
              fontWeight: '600',
              fontSize: '1.25em',
              marginTop: '1.5em',
              marginBottom: '0.5em',
            },
            h5: {
              color: '#fafafa',
              fontWeight: '600',
              fontSize: '1.125em',
            },
            strong: {
              color: '#fafafa',
              fontWeight: '600',
            },
            ul: {
              marginTop: '1.25em',
              marginBottom: '1.25em',
            },
            ol: {
              marginTop: '1.25em',
              marginBottom: '1.25em',
            },
            li: {
              marginTop: '0.5em',
              marginBottom: '0.5em',
            },
            code: {
              color: '#818CF8',
              backgroundColor: '#27272a',
              padding: '0.2em 0.4em',
              borderRadius: '0.25rem',
              fontWeight: '500',
              fontSize: '0.875em',
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
              borderRadius: '0.5rem',
              padding: '1.25rem 1.5rem',
              overflowX: 'auto',
              fontSize: '0.875em',
              lineHeight: '1.7',
            },
            'pre code': {
              backgroundColor: 'transparent',
              padding: '0',
              fontWeight: '400',
              color: '#fafafa',
            },
            blockquote: {
              fontWeight: '400',
              fontStyle: 'italic',
              color: '#a1a1aa',
              borderLeftWidth: '0.25rem',
              borderLeftColor: '#4F46E5',
              quotes: '"\\201C""\\201D""\\2018""\\2019"',
              marginTop: '1.6em',
              marginBottom: '1.6em',
              paddingLeft: '1em',
            },
            table: {
              width: '100%',
              tableLayout: 'auto',
              textAlign: 'left',
              marginTop: '2em',
              marginBottom: '2em',
              fontSize: '0.875em',
            },
            thead: {
              borderBottomWidth: '1px',
              borderBottomColor: '#3f3f46',
            },
            'thead th': {
              color: '#fafafa',
              fontWeight: '600',
              verticalAlign: 'bottom',
              paddingRight: '0.5em',
              paddingBottom: '0.5em',
              paddingLeft: '0.5em',
            },
            'tbody tr': {
              borderBottomWidth: '1px',
              borderBottomColor: '#3f3f46',
            },
            'tbody td': {
              verticalAlign: 'top',
              paddingTop: '0.5em',
              paddingRight: '0.5em',
              paddingBottom: '0.5em',
              paddingLeft: '0.5em',
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
