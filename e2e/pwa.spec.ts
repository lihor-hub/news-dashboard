/**
 * E2E tests for PWA install metadata.
 *
 * Split by what's available in dev vs build:
 *
 *  - iOS meta tags + theme-color: always present in index.html — tested here.
 *  - manifest link <link rel="manifest">: always present in index.html so the
 *    dev server and production build both expose install metadata.
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
  test('has app favicon and manifest links', async ({ page }) => {
    const favicon = page.locator('link[rel="icon"]');
    await expect(favicon).toHaveCount(1);
    expect(await favicon.getAttribute('href')).toBe('/favicon.svg');

    const manifest = page.locator('link[rel="manifest"]');
    await expect(manifest).toHaveCount(1);
    expect(await manifest.getAttribute('href')).toBe('/manifest.webmanifest');
  });

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

  test('manifest includes app favicon', async ({ page }) => {
    const response = await page.request.get('/manifest.webmanifest');
    const manifest = await response.json();
    const icons: Array<{ src: string; sizes: string; type: string }> = manifest.icons ?? [];
    const favicon = icons.find((i) => i.src === '/favicon.svg');
    expect(favicon).toBeDefined();
    expect(favicon?.sizes).toBe('any');
    expect(favicon?.type).toBe('image/svg+xml');
  });

  test('manifest includes maskable icon', async ({ page }) => {
    const response = await page.request.get('/manifest.webmanifest');
    const manifest = await response.json();
    const icons: Array<{ purpose: string }> = manifest.icons ?? [];
    expect(icons.some((i) => i.purpose === 'maskable')).toBe(true);
  });
});

test.describe('PWA — icon files', () => {
  test('GET /favicon.svg returns 200', async ({ page }) => {
    const response = await page.request.get('/favicon.svg');
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toContain('image/svg+xml');
  });

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
