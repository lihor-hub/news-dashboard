/**
 * E2E tests for PWA install metadata.
 *
 * Split by what's available in dev vs build:
 *
 *  - iOS meta tags + theme-color: always present in index.html — tested here.
 *  - manifest link <link rel="manifest">: injected by vite-plugin-pwa at
 *    BUILD time only (devOptions.enabled = false). Covered by the vitest
 *    pwa.test.ts unit tests and by `npm run build` in CI.
 *  - /manifest.webmanifest file: served from public/ in both dev and prod,
 *    so we verify its content here via fetch.
 */
import { test, expect } from '@playwright/test';
import { mockApi } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
});

test.describe('PWA — iOS meta tags', () => {
  test('has apple-mobile-web-app-capable meta tag', async ({ page }) => {
    const meta = page.locator('meta[name="apple-mobile-web-app-capable"]');
    await expect(meta).toHaveCount(1);
    expect(await meta.getAttribute('content')).toBe('yes');
  });

  test('has apple-mobile-web-app-title meta tag (≤12 chars)', async ({ page }) => {
    const meta = page.locator('meta[name="apple-mobile-web-app-title"]');
    await expect(meta).toHaveCount(1);
    const title = await meta.getAttribute('content');
    expect(title).toBeTruthy();
    expect((title ?? '').length).toBeLessThanOrEqual(12);
  });

  test('has apple-touch-icon link pointing to /icons/', async ({ page }) => {
    const link = page.locator('link[rel="apple-touch-icon"]');
    await expect(link).toHaveCount(1);
    const href = await link.getAttribute('href');
    expect(href).toContain('/icons/');
  });
});

test.describe('PWA — theme color', () => {
  test('has theme-color meta tag matching app charcoal', async ({ page }) => {
    const meta = page.locator('meta[name="theme-color"]');
    await expect(meta).toHaveCount(1);
    expect(await meta.getAttribute('content')).toBe('#221f1a');
  });
});

test.describe('PWA — manifest file', () => {
  test('GET /manifest.webmanifest returns 200', async ({ page }) => {
    const response = await page.request.get('/manifest.webmanifest');
    expect(response.status()).toBe(200);
  });

  test('manifest has required name and short_name', async ({ page }) => {
    const response = await page.request.get('/manifest.webmanifest');
    const manifest = await response.json();
    expect(manifest.name).toBeTruthy();
    expect(manifest.short_name).toBeTruthy();
    expect((manifest.short_name as string).length).toBeLessThanOrEqual(12);
  });

  test('manifest display is standalone', async ({ page }) => {
    const response = await page.request.get('/manifest.webmanifest');
    const manifest = await response.json();
    expect(manifest.display).toBe('standalone');
  });

  test('manifest includes 192×192 icon', async ({ page }) => {
    const response = await page.request.get('/manifest.webmanifest');
    const manifest = await response.json();
    const icons: Array<{ sizes: string; type: string }> = manifest.icons ?? [];
    const icon192 = icons.find((i) => i.sizes === '192x192');
    expect(icon192).toBeDefined();
    expect(icon192?.type).toBe('image/png');
  });

  test('manifest includes maskable icon', async ({ page }) => {
    const response = await page.request.get('/manifest.webmanifest');
    const manifest = await response.json();
    const icons: Array<{ purpose: string }> = manifest.icons ?? [];
    expect(icons.some((i) => i.purpose === 'maskable')).toBe(true);
  });
});

test.describe('PWA — icon files', () => {
  test('GET /icons/icon-192.png returns 200', async ({ page }) => {
    const response = await page.request.get('/icons/icon-192.png');
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toContain('image/png');
  });

  test('GET /icons/icon-512.png returns 200', async ({ page }) => {
    const response = await page.request.get('/icons/icon-512.png');
    expect(response.status()).toBe(200);
  });

  test('GET /icons/apple-touch-icon.png returns 200', async ({ page }) => {
    const response = await page.request.get('/icons/apple-touch-icon.png');
    expect(response.status()).toBe(200);
  });
});
