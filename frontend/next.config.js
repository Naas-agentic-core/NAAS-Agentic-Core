/** @type {import('next').NextConfig} */
const nextConfig = {
    reactStrictMode: false,
    async rewrites() {
      return [
        {
          source: '/api/:path*',
          destination: process.env.API_URL
            ? `${process.env.API_URL}/api/:path*`
            : 'http://127.0.0.1:8000/api/:path*',
        },
        {
            source: '/health',
            destination: process.env.API_URL
            ? `${process.env.API_URL}/health`
            : 'http://127.0.0.1:8000/health',
        },
        {
            source: '/admin/api/:path*',
            destination: process.env.API_URL
            ? `${process.env.API_URL}/admin/api/:path*`
            : 'http://127.0.0.1:8000/admin/api/:path*',
        }
      ]
    },
    allowedDevOrigins: ['*.replit.dev', '*.janeway.replit.dev', '*.replit.app'],
};

module.exports = nextConfig;
