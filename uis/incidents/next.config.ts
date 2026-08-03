import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  turbopack: {
    // Same fix as uis/backoffice: without this, Next.js gets confused by
    // the root-level package-lock.json and this app's own one.
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
