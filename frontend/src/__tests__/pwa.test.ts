// @vitest-environment happy-dom
/**
 * PWA manifest and meta-tag tests.
 *
 * These tests verify that the PWA configuration values match the app's
 * branding and that icons are declared at the required sizes.
 *
 * We read public/manifest.webmanifest directly so CI catches drift in the
 * install metadata served by both dev and production builds.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';

const MANIFEST = JSON.parse(
  readFileSync(resolve(process.cwd(), 'public/manifest.webmanifest'), 'utf-8')
) as {
  name: string;
  short_name: string;
  start_url: string;
  display: string;
  background_color: string;
  theme_color: string;
  icons: { src: string; sizes: string; type: string; purpose: string }[];
  share_target?: {
    action: string;
    method: string;
    params: { title: string; text: string; url: string };
  };
};

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
  it('declares the app favicon for browser and PWA metadata', () => {
    const icon = MANIFEST.icons.find((i) => i.src === '/favicon.svg');
    expect(icon).toBeDefined();
    expect(icon?.sizes).toBe('any');
    expect(icon?.type).toBe('image/svg+xml');
  });

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

  it('declares a PNG monochrome icon as primary (WebAPK minting compatibility)', () => {
    const icons = MANIFEST.icons.filter((i) => i.purpose === 'monochrome');
    expect(icons.length).toBeGreaterThanOrEqual(2);
    // PNG must come first — WebAPK minting processes explicit-size PNGs more reliably than SVG
    expect(icons[0].src).toBe('/icons/icon-monochrome-512.png');
    expect(icons[0].sizes).toBe('512x512');
    expect(icons[0].type).toBe('image/png');
    // SVG fallback for forward compat
    const svg = icons.find((i) => i.type === 'image/svg+xml');
    expect(svg?.src).toBe('/icons/icon-monochrome.svg');
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

describe('PWA manifest — share target', () => {
  it('accepts shared URLs through the app route', () => {
    expect(MANIFEST.share_target).toEqual({
      action: '/share-target',
      method: 'GET',
      params: { title: 'title', text: 'text', url: 'url' },
    });
  });
});
