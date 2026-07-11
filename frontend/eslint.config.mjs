import path from "path";
import { fileURLToPath } from "url";

import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Bridge legacy shareable configs (like `next/core-web-vitals`) into ESLint v9 flat config.
const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const config = [
  {
    // Mirror Next.js defaults: never lint build artifacts.
    ignores: ["**/.next/**", "**/out/**", "**/node_modules/**"],
  },
  ...compat.extends("next/core-web-vitals"),
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
];

export default config;
