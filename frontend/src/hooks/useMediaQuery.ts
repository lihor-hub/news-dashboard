import { useCallback, useMemo, useSyncExternalStore } from 'react';

/** Tailwind's `lg` breakpoint: the width where list pages gain a reading pane. */
export const DESKTOP_SPLIT_QUERY = '(min-width: 1024px)';

/** Live `window.matchMedia` result; `false` where matchMedia is unavailable. */
export function useMediaQuery(query: string): boolean {
  const mql = useMemo(
    () => (typeof window.matchMedia === 'function' ? window.matchMedia(query) : null),
    [query]
  );
  const subscribe = useCallback(
    (onChange: () => void) => {
      mql?.addEventListener('change', onChange);
      return () => mql?.removeEventListener('change', onChange);
    },
    [mql]
  );
  return useSyncExternalStore(
    subscribe,
    () => mql?.matches ?? false,
    () => false
  );
}
