import { X as XIcon, Highlighter } from 'lucide-react';
import type { ArticleHighlight } from '@/types';

export function ArticleHighlights({
  highlights,
  onDelete,
}: {
  highlights: ArticleHighlight[];
  onDelete: (highlightId: number) => void;
}) {
  if (highlights.length === 0) return null;

  return (
    <section
      className="mt-8 rounded-lg border border-border bg-surface/40 px-4 py-4"
      aria-label="Personal highlights"
    >
      <div className="mb-3 flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-subtle">
        <Highlighter className="size-3" strokeWidth={2} />
        Highlights
      </div>
      <ul className="space-y-3">
        {highlights.map((highlight) => (
          <li key={highlight.id} className="border-l-2 border-accent pl-3">
            <div className="flex items-start justify-between gap-3">
              <p className="text-[13px] leading-snug text-foreground">
                {highlight.highlighted_text}
              </p>
              <button
                type="button"
                onClick={() => onDelete(highlight.id)}
                className="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-surface hover:text-foreground"
                aria-label="Delete highlight"
              >
                <XIcon className="size-3.5" />
              </button>
            </div>
            {highlight.note ? (
              <p className="mt-1 text-[12px] leading-snug text-muted-foreground">
                {highlight.note}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
