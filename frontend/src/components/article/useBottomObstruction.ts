import { useEffect } from 'react';

/** CSS custom property (on <html>) read by the reader's floating UI. */
export const READER_BOTTOM_OFFSET_VAR = '--reader-bottom-offset';

// Clearance above an obstruction: the shell's raised Ask button protrudes
// 12px above the bottom bar, so leave room for it.
const RAISED_CLEARANCE_PX = 12;

/**
 * Height (px) covered by full-width fixed bars anchored in the lower half of
 * the viewport — the app shell's mobile bottom bar, the listen-queue player
 * stacked above it, etc. Measured from the DOM so the reader adapts to
 * whatever chrome its host renders, without coupling to those components.
 */
export function measureBottomObstruction(): number {
  const vh = window.innerHeight;
  const vw = window.innerWidth;
  let covered = 0;
  for (const el of document.querySelectorAll<HTMLElement>('nav, [role="region"]')) {
    if (el.closest('[data-reader-floating]')) continue;
    if (getComputedStyle(el).position !== 'fixed') continue;
    const rect = el.getBoundingClientRect();
    if (rect.height <= 0 || rect.width < vw * 0.6 || rect.top < vh / 2) continue;
    covered = Math.max(covered, vh - rect.top);
  }
  return covered > 0 ? Math.ceil(covered + RAISED_CLEARANCE_PX) : 0;
}

/**
 * While mounted, keeps `--reader-bottom-offset` on <html> in sync with the
 * bottom chrome so the portal-mounted action bar (which can't inherit vars
 * from its React parent) floats above it.
 */
export function useBottomObstruction(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    const root = document.documentElement;
    let frame = 0;
    let last = -1;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const next = measureBottomObstruction();
        if (next === last) return;
        last = next;
        root.style.setProperty(READER_BOTTOM_OFFSET_VAR, `${next}px`);
      });
    };
    update();
    // Chrome such as the listen-queue player mounts and unmounts at runtime.
    const observer = new MutationObserver(update);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener('resize', update);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener('resize', update);
      root.style.removeProperty(READER_BOTTOM_OFFSET_VAR);
    };
  }, [enabled]);
}
