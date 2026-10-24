import type { ReactNode } from 'react';
import { ChevronLeft, ChevronRight, ExternalLink, Download, Trash2 } from 'lucide-react';
import { isOfflineCacheSupported } from '@/lib/offline';
import { cn } from '@/lib/utils';

const iconBtn =
  'inline-flex size-11 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-surface md:size-9';

export function ArticleReaderHeader({
  goBack,
  goPrev,
  goNext,
  prevId,
  nextId,
  articleUrl,
  isShared,
  isSavedOffline,
  onSaveOffline,
  onRemoveOffline,
  progress,
  className,
}: {
  goBack?: () => void;
  goPrev: () => void;
  goNext: () => void;
  prevId: string | null;
  nextId: string | null;
  articleUrl: string;
  isShared: boolean;
  isSavedOffline: boolean;
  onSaveOffline: () => void;
  onRemoveOffline: () => void;
  /** Reading-progress indicator pinned to the header's top edge. */
  progress?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        'sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur',
        className
      )}
    >
      {progress}
      <div className="mx-auto flex h-14 max-w-2xl items-center justify-between gap-2 px-2 md:h-12 md:px-3">
        {goBack ? (
          <button
            onClick={goBack}
            className="inline-flex min-h-11 items-center gap-1 rounded-md px-2 text-[15px] text-muted-foreground hover:bg-surface hover:text-foreground md:min-h-9 md:text-sm"
          >
            <ChevronLeft className="size-5 rtl:-scale-x-100 md:size-4" /> Back
          </button>
        ) : (
          <span />
        )}
        <div className="flex items-center gap-0.5">
          <button
            onClick={goPrev}
            disabled={!prevId}
            className={cn(iconBtn, 'disabled:opacity-30')}
            aria-label="Previous article"
          >
            <ChevronLeft className="size-5 rtl:-scale-x-100 md:size-4" />
          </button>
          <button
            onClick={goNext}
            disabled={!nextId}
            className={cn(iconBtn, 'disabled:opacity-30')}
            aria-label="Next article"
          >
            <ChevronRight className="size-5 rtl:-scale-x-100 md:size-4" />
          </button>
          <a
            href={articleUrl}
            target="_blank"
            rel="noreferrer"
            className={iconBtn}
            aria-label="Open original"
          >
            <ExternalLink className="size-5 md:size-4" />
          </a>
          {isOfflineCacheSupported() && !isShared && (
            <button
              onClick={isSavedOffline ? onRemoveOffline : onSaveOffline}
              className={iconBtn}
              aria-label={isSavedOffline ? 'Remove offline save' : 'Save for offline'}
            >
              {isSavedOffline ? (
                <Trash2 className="size-5 md:size-4" />
              ) : (
                <Download className="size-5 md:size-4" />
              )}
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
