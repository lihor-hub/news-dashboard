import { useCallback, useSyncExternalStore } from 'react';

/** Tailwind's `lg` breakpoint: the width where list pages gain a reading pane. */
export const DESKTOP_SPLIT_QUERY = '(min-width: 1024px)';

/** Live `window.matchMedia` result; `false` where matchMedia is unavailable. */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (typeof window.matchMedia !== 'function') return () => undefined;
      const mql = window.matchMedia(query);
      mql.addEventListener('change', onChange);
      return () => mql.removeEventListener('change', onChange);
    },
    [query]
  );
  return useSyncExternalStore(
    subscribe,
    () => typeof window.matchMedia === 'function' && window.matchMedia(query).matches,
    () => false
  );
}
