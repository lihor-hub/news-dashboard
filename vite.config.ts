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
      // Let the plugin emit its external registration helper for the non-standard
      // root setup (index.html at repo root, not frontend/) and CSP script-src 'self'.
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
            // Article metadata/list JSON: prefer fresh network data, keep a bounded offline copy.
            urlPattern: ({ url }) =>
              url.origin === self.location.origin &&
              url.pathname === '/api/articles' &&
              !url.searchParams.has('include_archived'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'pwa-article-lists',
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 24, maxAgeSeconds: 60 * 60 * 24 * 7 },
              cacheableResponse: { statuses: [200] },
            },
          },
          {
            // Article bodies are explicit GETs so Workbox can serve opened/offline-saved reads.
            urlPattern: ({ url }) =>
              url.origin === self.location.origin &&
              /^\/api\/articles\/\d+\/body$/.test(url.pathname),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'offline-articles-v1',
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 * 30 },
              cacheableResponse: { statuses: [200] },
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
    rollupOptions: {
      output: {
        // Stable, always-needed-on-first-paint libraries get their own chunk
        // (independent from route/app code) so it caches across deploys and
        // stays under Vite's per-chunk size warning instead of ballooning
        // the app-shell "index" chunk every time application code changes.
        manualChunks(id) {
          if (
            /node_modules\/(react|react-dom|react-router|i18next|react-i18next|i18next-browser-languagedetector|@tanstack\/react-query|sonner)\//.test(
              id
            )
          ) {
            return 'vendor';
          }
        },
      },
    },
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
