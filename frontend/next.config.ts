import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  // Needed for Turbopack to resolve local linked/file dependencies in a monorepo.
  outputFileTracingRoot: path.join(__dirname, ".."),
  transpilePackages: ["hyper-scatter"],
  images: {
    unoptimized: true,
  },
  // Proxy API calls to backend during development
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:6262/api/:path*",
      },
    ];
  },
};

export default nextConfig;
