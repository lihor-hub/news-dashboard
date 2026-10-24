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
      className="mt-10 rounded-xl border border-border bg-surface/40 px-4 py-4 md:px-5"
      aria-label="Personal highlights"
    >
      <div className="mb-3 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-subtle">
        <Highlighter className="size-4" strokeWidth={1.75} />
        Highlights
      </div>
      <ul className="space-y-3">
        {highlights.map((highlight) => (
          <li key={highlight.id} className="border-s-2 border-accent ps-3">
            <div className="flex items-start justify-between gap-3">
              <p className="font-serif text-[15px] leading-relaxed text-foreground">
                {highlight.highlighted_text}
              </p>
              <button
                type="button"
                onClick={() => onDelete(highlight.id)}
                className="inline-flex size-11 shrink-0 md:size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-surface hover:text-foreground"
                aria-label="Delete highlight"
              >
                <XIcon className="size-4" />
              </button>
            </div>
            {highlight.note ? (
              <p className="mt-1 text-[13px] leading-snug text-muted-foreground md:text-xs">
                {highlight.note}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
