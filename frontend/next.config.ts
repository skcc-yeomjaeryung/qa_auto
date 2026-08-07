import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // `npm run build`가 실행 중인 dev 서버의 .next 캐시를 덮어써 500을 만들지 않게 분리한다.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
