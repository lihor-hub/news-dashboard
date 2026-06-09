import { useCallback, useEffect, useState } from 'react';
import { type Theme, applyTheme, getStoredTheme, setStoredTheme } from '../lib/theme';

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(getStoredTheme);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    setStoredTheme(next);
  }, []);

  // Re-apply when OS preference changes and theme is 'system'
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = () => {
      if (getStoredTheme() === 'system') applyTheme('system');
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  return { theme, setTheme };
}
