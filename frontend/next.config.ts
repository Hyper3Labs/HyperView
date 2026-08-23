import type { NextConfig } from "next";
import path from "path";

const isDev = process.env.NODE_ENV === "development";

const nextConfig: NextConfig = {
  ...(!isDev ? { output: "export" as const, trailingSlash: true } : {}),
  ...(isDev ? { skipTrailingSlashRedirect: true } : {}),
  // Needed for Turbopack to resolve local linked/file dependencies in a monorepo.
  outputFileTracingRoot: path.join(__dirname, ".."),
  transpilePackages: ["hyper-scatter"],
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  env: {
    NEXT_PUBLIC_HYPERVIEW_API_BASE:
      process.env.NEXT_PUBLIC_HYPERVIEW_API_BASE ??
      (isDev ? "http://127.0.0.1:6262" : ""),
  },
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
