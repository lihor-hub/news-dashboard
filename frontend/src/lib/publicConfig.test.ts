import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchPublicConfig } from './publicConfig';

function configResponse(title: string, baseUrl = 'https://dify.example.test'): Response {
  return new Response(
    JSON.stringify({
      dify: {
        enabled: true,
        base_url: baseUrl,
        app_token: 'public-embed-token',
        title,
      },
    }),
    {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('fetchPublicConfig', () => {
  it('rejects a Dify iframe on the News Dashboard origin', async () => {
    const happyDom = (
      window as typeof window & {
        happyDOM?: { setURL: (url: string) => void };
      }
    ).happyDOM;
    if (!happyDom) throw new Error('Happy DOM API is required for this browser-boundary test');

    const previousUrl = window.location.href;
    happyDom.setURL('https://news.example.test/inbox');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(configResponse('News Assistant', 'https://news.example.test'))
    );

    try {
      await expect(fetchPublicConfig()).rejects.toThrow('Invalid public configuration');
    } finally {
      happyDom.setURL(previousUrl);
    }
  });

  it('accepts 120 non-BMP Unicode code points like the Python validator', async () => {
    const title = '😀'.repeat(120);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(configResponse(title)));

    await expect(fetchPublicConfig()).resolves.toMatchObject({
      dify: { enabled: true, title },
    });
  });

  it('rejects a title beyond the shared 120-code-point limit', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(configResponse('😀'.repeat(121))));

    await expect(fetchPublicConfig()).rejects.toThrow('Invalid public configuration');
  });
});
