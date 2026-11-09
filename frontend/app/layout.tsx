import type { Metadata, Viewport } from 'next'
import '@fontsource-variable/montserrat'
import './globals.css'

export const metadata: Metadata = {
  title: 'Deal Intelligence — Blue Commercial Properties',
  description: 'Automated deal analysis, lease abstraction, and RSF reconciliation for commercial real estate buyers',
  icons: {
    icon: [{ url: '/icon-32.png', sizes: '32x32', type: 'image/png' }, { url: '/icon-192.png', sizes: '192x192', type: 'image/png' }],
    apple: '/apple-icon.png',
  },
  appleWebApp: { capable: true, title: 'Blue CPM Deals', statusBarStyle: 'default' },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: '#ffffff',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className="bg-background">
      <body className="font-sans antialiased">
        {children}
      </body>
    </html>
  )
}
