import { useMutation } from '@tanstack/react-query';
import { Loader2, Scale } from 'lucide-react';
import { fetchArticlePerspectives } from '@/api';

export function ArticlePerspectives({ articleId }: { articleId: string }) {
  const perspectivesMutation = useMutation({
    mutationFn: () => fetchArticlePerspectives(articleId),
  });

  return (
    <>
      {perspectivesMutation.isIdle && (
        <button
          onClick={() => perspectivesMutation.mutate()}
          data-testid="perspectives-button"
          className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-border bg-surface/40 px-3 py-1.5 text-[12px] font-medium text-muted-foreground hover:text-foreground hover:bg-surface transition-colors"
        >
          <Scale className="size-3.5" strokeWidth={1.75} />
          Context &amp; Perspectives
        </button>
      )}
      {perspectivesMutation.isPending && (
        <div className="mt-4 rounded-lg border border-border bg-surface/40 px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            <span>Analyzing perspectives…</span>
          </div>
        </div>
      )}
      {perspectivesMutation.isSuccess && (
        <div
          className="mt-4 rounded-lg border border-border bg-surface/40 px-4 py-4"
          data-testid="perspectives-section"
        >
          <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-subtle mb-3">
            <Scale className="size-3" strokeWidth={2} />
            Context &amp; Perspectives
          </div>
          {[
            {
              label: 'Facts Verified',
              items: perspectivesMutation.data.verified_facts,
              color: 'text-emerald-500',
            },
            {
              label: 'Missing Context',
              items: perspectivesMutation.data.omissions,
              color: 'text-amber-500',
            },
            {
              label: 'Differing Opinions',
              items: perspectivesMutation.data.alternative_perspectives,
              color: 'text-blue-400',
            },
          ]
            .filter((section) => section.items.length > 0)
            .map((section) => (
              <div key={section.label} className="mb-3 last:mb-0">
                <div
                  className={`text-[10px] font-semibold uppercase tracking-wide mb-1 ${section.color}`}
                >
                  {section.label}
                </div>
                <ul className="space-y-1">
                  {section.items.map((item, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 text-[13px] leading-snug text-foreground"
                    >
                      <span className={`mt-0.5 shrink-0 ${section.color}`}>•</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          {perspectivesMutation.data.verified_facts.length === 0 &&
            perspectivesMutation.data.omissions.length === 0 &&
            perspectivesMutation.data.alternative_perspectives.length === 0 && (
              <p className="text-[13px] text-muted-foreground">
                No additional context available for this article.
              </p>
            )}
        </div>
      )}
    </>
  );
}
