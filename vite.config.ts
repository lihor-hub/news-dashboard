import path from 'path';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      // Inline the service worker registration so it works with the non-standard
      // root setup (index.html at repo root, not frontend/).
      injectRegister: 'auto',
      // Only apply PWA in production builds — dev mode uses Vite HMR.
      devOptions: { enabled: false },
      includeAssets: [
        'favicon.ico',
        'favicon.svg',
        'manifest.webmanifest',
        'icons/apple-touch-icon.png',
        'icons/icon-192.png',
        'icons/icon-512.png',
        'icons/icon-512-maskable.png',
        'icons/icon-monochrome-512.png',
        'icons/icon-monochrome.svg',
      ],
      manifest: false,
      workbox: {
        // Cache the app shell and static assets, but never let the service worker
        // answer backend/auth navigations.  Otherwise `/auth/login` can be served
        // as the SPA fallback and Keycloak redirects never reach the server.
        globPatterns: ['**/*.{js,css,html,svg,ico,woff2}'],
        navigateFallbackDenylist: [/^\/api\//, /^\/auth\//, /^\/keycloak\//],
        // Add push notification event handlers to the generated service worker.
        importScripts: ['/push-handler.js'],
        runtimeCaching: [
          {
            // Font assets: cache-first, 1 year TTL
            urlPattern: /\.(?:woff2)$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'pwa-fonts',
              expiration: {
                maxEntries: 10,
                maxAgeSeconds: 60 * 60 * 24 * 365,
              },
            },
          },
          {
            // Icon/image assets: cache-first, long TTL
            urlPattern: /\/icons\/.+\.(png|svg|webp|ico)$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'pwa-images',
              expiration: { maxEntries: 20, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
          {
            // Article list/search responses: serve stale copy instantly while
            // revalidating, and fall back to it entirely when offline.
            urlPattern: /^\/api\/(articles|search)(\?.*)?$/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'api-article-lists',
              expiration: { maxEntries: 30, maxAgeSeconds: 60 * 60 * 24 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            // Single article metadata: prefer the network, fall back to the
            // last-seen copy so a previously opened article still renders.
            urlPattern: /^\/api\/articles\/\d+$/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-article-detail',
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 14 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            // Article body fetch is a POST; cache it too so a previously read
            // article's body is available with no network.
            urlPattern: /^\/api\/articles\/\d+\/body$/,
            method: 'POST',
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-article-body',
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 14 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
    }),
  ],
  root: '.',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'frontend/src'),
    },
  },
  build: {
    outDir: 'frontend/dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    setupFiles: ['./frontend/src/test-setup.ts'],
    include: ['frontend/src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['frontend/src/**'],
      exclude: ['frontend/src/**/*.test.{ts,tsx}', 'frontend/src/test-setup.ts'],
    },
  },
});
