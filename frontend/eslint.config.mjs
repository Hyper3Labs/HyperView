import nextCoreWebVitals from "eslint-config-next/core-web-vitals";

const config = [
  {
    // Mirror Next.js defaults: never lint build artifacts.
    ignores: ["**/.next/**", "**/out/**", "**/node_modules/**"],
  },
  ...nextCoreWebVitals,
  {
    // HyperView uses React 18 without the React Compiler. Keep the standard
    // hooks rules while excluding compiler-only diagnostics.
    rules: {
      "react-hooks/incompatible-library": "off",
      "react-hooks/preserve-manual-memoization": "off",
      "react-hooks/refs": "off",
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/static-components": "off",
    },
  },
  {
    files: ["src/panels/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "@/store/useStore",
              message: "Panels must access runtime state through @/panel-sdk.",
              allowTypeImports: true,
            },
            {
              name: "@/lib/api",
              message: "Panels must access data and commands through @/panel-sdk.",
              allowTypeImports: true,
            },
          ],
        },
      ],
    },
  },
  {
    files: [
      "src/panels/builtins/**/*.{ts,tsx}",
      "src/components/ExplorerPanel.tsx",
    ],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "dockview-react",
              message: "Panels receive host context through @/panel-sdk, not Dockview props.",
              allowTypeImports: false,
            },
            {
              name: "@/store/useStore",
              message: "Panels must access runtime state through @/panel-sdk.",
              allowTypeImports: true,
            },
            {
              name: "@/lib/api",
              message: "Panels must access data and commands through @/panel-sdk.",
              allowTypeImports: true,
            },
          ],
        },
      ],
    },
  },
];

export default config;
