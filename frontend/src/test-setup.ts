import '@testing-library/jest-dom';
import { afterEach, beforeEach, vi } from 'vitest';

// Guard against accidental real network calls: any test that doesn't stub `fetch`
// itself (via vi.stubGlobal, vi.spyOn on an api function, etc.) gets this default,
// which rejects with an actionable message instead of hitting the real network.
// Tests that install their own fetch mock in a `beforeEach` run after this one and
// simply override it.
function unmockedFetchUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function unmockedFetch(input: RequestInfo | URL): Promise<never> {
  const url = unmockedFetchUrl(input);
  return Promise.reject(
    new Error(
      `Unmocked fetch() call to "${url}" in a test. Stub this request explicitly ` +
        `(e.g. vi.stubGlobal('fetch', ...) or vi.spyOn(api, '...')).`
    )
  );
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(unmockedFetch));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// Node.js v26 provides an experimental localStorage global that is non-functional
// without --localstorage-file. Replace it with an in-memory implementation so
// tests that exercise localStorage (theme, etc.) work in any Node environment.
const store: Record<string, string> = {};
const localStorageMock: Storage = {
  getItem: (key) => store[key] ?? null,
  setItem: (key, value) => {
    store[key] = value;
  },
  removeItem: (key) => {
    delete store[key];
  },
  clear: () => {
    Object.keys(store).forEach((k) => delete store[k]);
  },
  key: (index) => Object.keys(store)[index] ?? null,
  get length() {
    return Object.keys(store).length;
  },
};
Object.defineProperty(globalThis, 'localStorage', {
  value: localStorageMock,
  configurable: true,
  writable: true,
});
