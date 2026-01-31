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
];

export default config;
