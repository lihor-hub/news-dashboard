export type Theme = 'light' | 'dark' | 'system';

const STORAGE_KEY = 'theme';

function resolveApplied(theme: Theme): 'light' | 'dark' {
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return theme;
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', resolveApplied(theme));
}

export function getStoredTheme(): Theme {
  return (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? 'system';
}

export function setStoredTheme(theme: Theme): void {
  localStorage.setItem(STORAGE_KEY, theme);
  applyTheme(theme);
}

/** Run once before React renders to avoid FOUC. */
export function initTheme(): void {
  applyTheme(getStoredTheme());
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (getStoredTheme() === 'system') applyTheme('system');
  });
}
