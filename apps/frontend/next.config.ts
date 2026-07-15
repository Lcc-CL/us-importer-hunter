import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for the slim production Docker image (see Dockerfile prod stage)
  output: "standalone",
};

export default nextConfig;
