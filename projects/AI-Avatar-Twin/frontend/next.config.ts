import type { NextConfig } from 'next';
const config: NextConfig = {
    output: 'standalone',
    experimental: { proxyTimeout: 240000 },
    async rewrites() {
        return [{ source: '/api/:path*', destination: `${process.env.BACKEND_URL || 'http://127.0.0.1:8100'}/api/:path*` }];
    },
};
export default config;
