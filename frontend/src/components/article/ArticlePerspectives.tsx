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
          className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-border bg-background px-3.5 text-[13px] font-medium text-muted-foreground transition-colors hover:bg-surface hover:text-foreground md:min-h-9 md:text-xs"
        >
          <Scale className="size-4" strokeWidth={1.75} />
          Context &amp; Perspectives
        </button>
      )}
      {perspectivesMutation.isPending && (
        <div className="w-full basis-full rounded-lg border border-border bg-background px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            <span>Analyzing perspectives…</span>
          </div>
        </div>
      )}
      {perspectivesMutation.isSuccess && (
        <div
          className="w-full basis-full rounded-lg border border-border bg-background px-4 py-4"
          data-testid="perspectives-section"
        >
          <div className="mb-3 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-subtle">
            <Scale className="size-4" strokeWidth={1.75} />
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
                  className={`mb-1 text-xs font-semibold uppercase tracking-wide ${section.color}`}
                >
                  {section.label}
                </div>
                <ul className="space-y-1">
                  {section.items.map((item, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 text-[14px] leading-snug text-foreground"
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
              <p className="text-[14px] text-muted-foreground">
                No additional context available for this article.
              </p>
            )}
        </div>
      )}
    </>
  );
}
