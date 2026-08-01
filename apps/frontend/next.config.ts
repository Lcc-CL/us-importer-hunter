import type { NextConfig } from "next";

/**
 * Server-only backend address. When set (production on Zeabur), the Next.js
 * server proxies the allow-listed API paths below over the private network —
 * the browser only ever talks to this same-origin frontend, and the backend
 * needs no public domain. Never expose this value with a NEXT_PUBLIC_ prefix.
 *
 * Local development leaves it unset: the browser talks to the backend
 * directly via NEXT_PUBLIC_API_BASE_URL (defaults to http://localhost:8000).
 */
const BACKEND_INTERNAL_URL = (process.env.BACKEND_INTERNAL_URL ?? "").replace(/\/$/, "");

const nextConfig: NextConfig = {
  // Required for the slim production Docker image (see Dockerfile prod stage)
  output: "standalone",

  async rewrites() {
    if (!BACKEND_INTERNAL_URL) return [];
    // Allow-list, not a blanket proxy: exactly the surfaces the MVP uses —
    // research (runs / history / confirm / contact discovery), prospect
    // analyze / reload / approve / decision-maker confirm, import evidence,
    // and the provider badge. Nothing else is reachable through the frontend.
    return [
      "/api/v1/health/runtime",
      "/api/v1/research/:path*",
      "/api/v1/mvp/:path*",
      "/api/v1/companies/:path*",
      "/api/v1/discovery-tasks/:path*",
      "/api/v1/prospect-batches/:path*",
      "/api/v1/calibrations/:path*",
    ].map((source) => ({
      source,
      destination: `${BACKEND_INTERNAL_URL}${source}`,
    }));
  },
};

export default nextConfig;
