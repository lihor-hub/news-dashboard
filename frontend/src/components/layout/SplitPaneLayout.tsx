import type { ReactNode, Ref } from 'react';
import { cn } from '@/lib/utils';
import { useBottomObstruction } from '@/components/article/useBottomObstruction';

// Both panes end at the viewport bottom, so reserve room for fixed bottom
// chrome (e.g. the listen-queue player) measured by useBottomObstruction.
const CLEAR_BOTTOM_CHROME = 'pb-[var(--reader-bottom-offset,0px)]';

interface SplitPaneLayoutProps {
  /** Pinned above the list scroller (title, filters, banners). */
  listHeader?: ReactNode;
  list: ReactNode;
  detail: ReactNode;
  listLabel: string;
  detailLabel: string;
  /** The list's own scroll container, for keeping the selection in view. */
  listScrollRef?: Ref<HTMLDivElement>;
  className?: string;
}

/**
 * Desktop list + reading pane. Each pane scrolls on its own; the host
 * (AppShell) sizes the layout to the viewport when `[data-split-pane]` is
 * present, so this fills whatever height it is given.
 */
export function SplitPaneLayout({
  listHeader,
  list,
  detail,
  listLabel,
  detailLabel,
  listScrollRef,
  className,
}: SplitPaneLayoutProps) {
  useBottomObstruction(true);
  return (
    <div
      data-split-pane
      data-testid="split-pane"
      className={cn(
        'grid min-h-0 grid-cols-[clamp(380px,32vw,440px)_minmax(0,1fr)] border-t border-border',
        className
      )}
    >
      <section aria-label={listLabel} className="flex min-h-0 flex-col border-e border-border">
        {listHeader && <div className="shrink-0">{listHeader}</div>}
        <div ref={listScrollRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          <div className={CLEAR_BOTTOM_CHROME}>{list}</div>
        </div>
      </section>
      <section aria-label={detailLabel} className={cn('min-h-0 min-w-0', CLEAR_BOTTOM_CHROME)}>
        {detail}
      </section>
    </div>
  );
}
