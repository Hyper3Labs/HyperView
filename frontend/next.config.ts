import type { NextConfig } from "next";
import path from "path";

const isDev = process.env.NODE_ENV === "development";

const nextConfig: NextConfig = {
  ...(!isDev ? { output: "export" as const, trailingSlash: true } : {}),
  ...(isDev ? { skipTrailingSlashRedirect: true } : {}),
  // Needed for Turbopack to resolve local linked/file dependencies in a monorepo.
  outputFileTracingRoot: path.join(__dirname, ".."),
  transpilePackages: ["hyper-scatter"],
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
