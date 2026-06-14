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
      manifest: {
        name: 'News Dashboard',
        short_name: 'News',
        description: 'Personal AI-curated news dashboard',
        start_url: '/',
        display: 'standalone',
        background_color: '#faf8f5',
        theme_color: '#221f1a',
        lang: 'en',
        icons: [
          {
            src: '/icons/icon-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any',
          },
          {
            src: '/icons/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any',
          },
          {
            src: '/icons/icon-512-maskable.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // Cache the app shell (JS/CSS/HTML) with a StaleWhileRevalidate strategy
        // so the app loads instantly and updates in the background.
        //
        // API calls (/api/**) are intentionally NOT cached — news data must be
        // fresh and caching it would show stale articles or briefings offline.
        globPatterns: ['**/*.{js,css,html,svg,woff2}'],
        runtimeCaching: [
          {
            // Icon/image assets: cache-first, long TTL
            urlPattern: /\/icons\/.+\.(png|svg|webp|ico)$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'pwa-images',
              expiration: { maxEntries: 20, maxAgeSeconds: 60 * 60 * 24 * 30 },
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
      reporter: ['text'],
      include: ['frontend/src/**'],
      exclude: ['frontend/src/**/*.test.{ts,tsx}', 'frontend/src/test-setup.ts'],
    },
  },
});
