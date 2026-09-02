import type { NextConfig } from "next";
import path from "path";

const isDev = process.env.NODE_ENV === "development";

const nextConfig: NextConfig = {
  // Relative asset URLs make an exported bundle location-independent: the same
  // files work at "/", at "/spaces/abo-catalog/", or anywhere else, with no
  // build-time knowledge of where they will be served from. Without this Next
  // bakes root-absolute "/_next/..." into the shell and every bundle published
  // under a subpath 404s its own JS and CSS.
  ...(!isDev
    ? { output: "export" as const, trailingSlash: true, assetPrefix: "./" }
    : {}),
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
