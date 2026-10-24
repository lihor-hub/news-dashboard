import { useEffect, useState, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';

function measure(container: HTMLElement | null): number {
  const scrolled = container ? container.scrollTop : window.scrollY;
  const total = container
    ? container.scrollHeight - container.clientHeight
    : document.documentElement.scrollHeight - window.innerHeight;
  if (total <= 0) return 0;
  return Math.min(1, Math.max(0, scrolled / total));
}

/**
 * Fraction (0–1) of the reader that has been scrolled. Tracks the window when
 * `containerRef` is omitted (full-page reader) or the given element when the
 * reader scrolls inside its own pane.
 */
function useReadingProgress(containerRef?: RefObject<HTMLElement | null>) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const container = containerRef?.current ?? null;
    const target: HTMLElement | Window = container ?? window;
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setProgress(measure(container)));
    };
    update();
    target.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    return () => {
      cancelAnimationFrame(frame);
      target.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, [containerRef]);

  return progress;
}

/** Thin bar pinned to the top edge of the reader header. */
export function ReadingProgress({
  containerRef,
}: {
  containerRef?: RefObject<HTMLElement | null>;
}) {
  const { t } = useTranslation();
  const progress = useReadingProgress(containerRef);
  const percent = Math.round(progress * 100);

  return (
    <div
      role="progressbar"
      aria-label={t('reader.progress', 'Reading progress')}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      className="pointer-events-none absolute inset-x-0 top-0 h-0.5 overflow-hidden"
    >
      <div
        className="h-full origin-left bg-accent transition-transform duration-150 ease-out motion-reduce:transition-none rtl:origin-right"
        style={{ transform: `scaleX(${progress})` }}
      />
    </div>
  );
}
