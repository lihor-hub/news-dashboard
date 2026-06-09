import '@testing-library/jest-dom';

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
