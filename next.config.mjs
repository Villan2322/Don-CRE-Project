/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    unoptimized: true,
  },
  // On Vercel, /backend is routed to the Python service by vercel.json.
  // Locally, run `uvicorn main:app --port 8000` in backend/ and this proxies to it.
  async rewrites() {
    if (process.env.VERCEL) return []
    return [
      {
        source: '/backend/:path*',
        destination: `${process.env.BACKEND_URL || 'http://localhost:8000'}/:path*`,
      },
    ]
  },
}

export default nextConfig
