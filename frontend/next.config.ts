import type { NextConfig } from "next";

// 服务端代理目标（node 侧变量，不会暴露给浏览器）
const API_BASE = process.env.API_PROXY_TARGET || "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  /**
   * 开发/生产都走同源代理：
   * 前端请求 /api/v1/* → 后端 API，避免 CORS 与 Cookie 问题。
   * 前端代码统一用相对路径调用（src/lib/api.ts 的 BASE 默认空）。
   */
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${API_BASE}/api/v1/:path*`,
      },
      {
        source: "/static/:path*",
        destination: `${API_BASE}/static/:path*`,
      },
    ];
  },
};

export default nextConfig;
