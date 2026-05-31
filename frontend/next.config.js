/** @type {import('next').NextConfig} */
const path = require('path');

// Security headers applied to every response from the Next.js app.
// CSP allows the app's own origin, Stripe (Checkout/Elements), and the API
// origin(s) for XHR/fetch. 'unsafe-inline'/'unsafe-eval' are required by Next's
// runtime (no nonce pipeline); everything else is locked down, and
// frame-ancestors 'none' blocks clickjacking.
const API_ORIGINS = [
  'https://proreadyengineer-api.onrender.com',
  'https://proreadyengineer-api-staging.onrender.com',
  'https://api.promechdirectory.com',
];

const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://js.stripe.com",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https:",
  "font-src 'self' data:",
  `connect-src 'self' ${API_ORIGINS.join(' ')} https://api.stripe.com https://js.stripe.com`,
  "frame-src https://js.stripe.com https://hooks.stripe.com",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join('; ');

const securityHeaders = [
  { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
  { key: 'Content-Security-Policy', value: csp },
];

const nextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: false,
  },
  images: {
    unoptimized: true,
  },
  async headers() {
    return [
      { source: '/:path*', headers: securityHeaders },
    ];
  },
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      '@': path.resolve(__dirname, 'src'),
    };
    return config;
  },
}

module.exports = nextConfig
