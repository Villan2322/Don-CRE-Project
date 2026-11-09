/** @type {import('next').NextConfig} */
const isDev = process.env.NODE_ENV !== 'production'

const nextConfig = {
  // Production builds are plain static files that the Python server serves.
  output: isDev ? undefined : 'export',
  images: {
    unoptimized: true,
  },
  // In `npm run dev`, send /api to the Python server (uvicorn on :8000 by default).
  ...(isDev && {
    async rewrites() {
      return [
        {
          source: '/api/:path*',
          destination: `${process.env.BACKEND_URL || 'http://localhost:8000'}/api/:path*`,
        },
      ]
    },
  }),
}

export default nextConfig
