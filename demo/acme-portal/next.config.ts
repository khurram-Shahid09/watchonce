import type { NextConfig } from "next";

// Deliberately plain: every page is rendered per request (cookies decide the session and UI variant).
const nextConfig: NextConfig = {
  poweredByHeader: false,
};

export default nextConfig;
