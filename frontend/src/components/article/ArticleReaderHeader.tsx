import { ChevronLeft, ChevronRight, ExternalLink, Download } from 'lucide-react';
import { isOfflineCacheSupported } from '@/lib/offline';

export function ArticleReaderHeader({
  goBack,
  goPrev,
  goNext,
  prevId,
  nextId,
  articleUrl,
  isShared,
  onSaveOffline,
}: {
  goBack: () => void;
  goPrev: () => void;
  goNext: () => void;
  prevId: string | null;
  nextId: string | null;
  articleUrl: string;
  isShared: boolean;
  onSaveOffline: () => void;
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur">
      <div className="mx-auto max-w-2xl flex h-12 items-center justify-between px-3">
        <button
          onClick={goBack}
          className="inline-flex items-center gap-1 px-2 py-1 -ml-1 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-surface"
        >
          <ChevronLeft className="size-4" /> Back
        </button>
        <div className="flex items-center gap-1">
          <button
            onClick={goPrev}
            disabled={!prevId}
            className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-surface disabled:opacity-30"
            aria-label="Previous article"
          >
            <ChevronLeft className="size-4" />
          </button>
          <button
            onClick={goNext}
            disabled={!nextId}
            className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-surface disabled:opacity-30"
            aria-label="Next article"
          >
            <ChevronRight className="size-4" />
          </button>
          <a
            href={articleUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-surface"
            aria-label="Open original"
          >
            <ExternalLink className="size-4" />
          </a>
          {isOfflineCacheSupported() && !isShared && (
            <button
              onClick={onSaveOffline}
              className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-surface"
              aria-label="Save for offline"
            >
              <Download className="size-4" />
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
