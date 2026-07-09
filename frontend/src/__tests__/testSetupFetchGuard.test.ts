import { describe, expect, it } from 'vitest';

describe('test-setup fetch guard', () => {
  it('rejects an unmocked fetch call, naming the requested URL', async () => {
    await expect(fetch('/api/definitely-not-mocked')).rejects.toThrow('/api/definitely-not-mocked');
  });

  it('rejects an unmocked fetch call given a Request object, naming its URL', async () => {
    const request = new Request('https://example.test/api/thing');
    await expect(fetch(request)).rejects.toThrow('https://example.test/api/thing');
  });
});
