import { describe, it, expect } from 'vitest';
import { isChunkLoadError } from '../chunkError';

describe('isChunkLoadError', () => {
  it('returns false for non-Error values', () => {
    expect(isChunkLoadError('boom')).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
    expect(isChunkLoadError(undefined)).toBe(false);
  });

  it('returns false for an unrelated Error', () => {
    expect(isChunkLoadError(new Error('network timeout'))).toBe(false);
  });

  it('returns true for a stale dynamic import failure message', () => {
    expect(isChunkLoadError(new Error('Failed to fetch dynamically imported module: /a.js'))).toBe(
      true
    );
    expect(isChunkLoadError(new Error('error loading dynamically imported module: /b.js'))).toBe(
      true
    );
    expect(isChunkLoadError(new Error('Importing a module script failed'))).toBe(true);
  });
});
