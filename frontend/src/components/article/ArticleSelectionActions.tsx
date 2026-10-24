import { Highlighter, Share2 } from 'lucide-react';

export function ArticleSelectionActions({
  selectedText,
  isShared,
  onHighlight,
  onShare,
}: {
  selectedText: string;
  isShared: boolean;
  onHighlight: () => void;
  onShare: () => void;
}) {
  if (!selectedText) return null;

  // RTL exception: left 50% pairs with translateX(-50%) to center the action bar.
  return (
    <div className="fixed bottom-[calc(env(safe-area-inset-bottom)+var(--app-bottom-nav-height,0px)+5.5rem)] left-1/2 z-30 flex -translate-x-1/2 items-center gap-1 rounded-full border border-border bg-background p-1 shadow-lg">
      {!isShared ? (
        <button
          type="button"
          onClick={onHighlight}
          className="inline-flex min-h-11 items-center gap-2 rounded-full px-4 text-sm font-medium text-foreground hover:bg-surface md:min-h-9"
        >
          <Highlighter className="size-4" strokeWidth={1.75} />
          Highlight
        </button>
      ) : null}
      <button
        type="button"
        onClick={onShare}
        aria-label="Share selected text"
        className="inline-flex min-h-11 items-center gap-2 rounded-full px-4 text-sm font-medium text-foreground hover:bg-surface md:min-h-9"
      >
        <Share2 className="size-4" strokeWidth={1.75} />
        Share
      </button>
    </div>
  );
}
