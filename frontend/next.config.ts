import type { NextConfig } from "next";

const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Off on purpose: Next gzips proxied responses for any browser (Accept-Encoding), and gzip holds the small
  // SSE messages of /api/stream back, so live updates never arrive. curl sends no Accept-Encoding and hides this.
  compress: false,
  // The UI calls /api/* on its own origin (no CORS); Next forwards it to the FastAPI backend.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
