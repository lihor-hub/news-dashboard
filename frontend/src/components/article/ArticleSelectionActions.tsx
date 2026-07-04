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

  return (
    <div className="fixed bottom-20 left-1/2 z-30 flex -translate-x-1/2 items-center gap-2 rounded-md border border-border bg-background p-1 shadow-lg">
      {!isShared ? (
        <button
          type="button"
          onClick={onHighlight}
          className="inline-flex items-center gap-2 rounded px-3 py-2 text-sm font-medium text-foreground hover:bg-surface"
        >
          <Highlighter className="size-4" strokeWidth={1.75} />
          Highlight
        </button>
      ) : null}
      <button
        type="button"
        onClick={onShare}
        aria-label="Share selected text"
        className="inline-flex items-center gap-2 rounded px-3 py-2 text-sm font-medium text-foreground hover:bg-surface"
      >
        <Share2 className="size-4" strokeWidth={1.75} />
        Share
      </button>
    </div>
  );
}
