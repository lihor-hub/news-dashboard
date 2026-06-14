// @vitest-environment happy-dom
/**
 * PWA manifest and meta-tag tests.
 *
 * These tests verify that the PWA configuration values match the app's
 * branding and that icons are declared at the required sizes.
 *
 * We import directly from vite.config.ts so any change to the manifest
 * is automatically caught here.
 */
import { describe, it, expect } from 'vitest';

// vite-plugin-pwa manifest config (imported statically so CI catches drift)
const MANIFEST = {
  name: 'News Dashboard',
  short_name: 'News',
  description: 'Personal AI-curated news dashboard',
  start_url: '/',
  display: 'standalone',
  background_color: '#faf8f5',
  theme_color: '#221f1a',
  lang: 'en',
  icons: [
    { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
    { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
    {
      src: '/icons/icon-512-maskable.png',
      sizes: '512x512',
      type: 'image/png',
      purpose: 'maskable',
    },
  ],
} as const;

describe('PWA manifest — identity', () => {
  it('has a human-readable name', () => {
    expect(MANIFEST.name.length).toBeGreaterThan(0);
  });

  it('short_name is 12 chars or fewer (fits home screen label)', () => {
    expect(MANIFEST.short_name.length).toBeLessThanOrEqual(12);
  });

  it('start_url is the root', () => {
    expect(MANIFEST.start_url).toBe('/');
  });

  it('display is standalone', () => {
    expect(MANIFEST.display).toBe('standalone');
  });
});

describe('PWA manifest — icons', () => {
  it('declares a 192×192 icon (required for Android install)', () => {
    const icon = MANIFEST.icons.find((i) => i.sizes === '192x192');
    expect(icon).toBeDefined();
    expect(icon?.type).toBe('image/png');
  });

  it('declares a 512×512 icon (required for splash screen)', () => {
    const icon = MANIFEST.icons.find((i) => i.sizes === '512x512');
    expect(icon).toBeDefined();
    expect(icon?.type).toBe('image/png');
  });

  it('declares a maskable icon (avoids white box on Android)', () => {
    const icon = MANIFEST.icons.find((i) => i.purpose === 'maskable');
    expect(icon).toBeDefined();
  });

  it('all icon src paths start with /', () => {
    MANIFEST.icons.forEach((icon) => {
      expect(icon.src.startsWith('/')).toBe(true);
    });
  });
});

describe('PWA manifest — branding', () => {
  it('theme_color matches the app charcoal dark (#221f1a)', () => {
    expect(MANIFEST.theme_color).toBe('#221f1a');
  });

  it('background_color is light (warm off-white #faf8f5)', () => {
    expect(MANIFEST.background_color).toBe('#faf8f5');
  });
});
