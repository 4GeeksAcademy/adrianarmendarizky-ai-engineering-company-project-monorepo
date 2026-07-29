import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  turbopack: {
    // Root set to monorepo root (two levels up from uis/backoffice/) so
    // Turbopack can resolve imports from src/ without an alias.
    // The backoffice has no .env.local, so the wider root causes no issue.
    root: path.resolve(__dirname, "../.."),
  },
};

export default nextConfig;
