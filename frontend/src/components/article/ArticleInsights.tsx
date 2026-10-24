import { useEffect } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Loader2, Sparkles } from 'lucide-react';
import { fetchArticleInsights } from '@/api';

export function ArticleInsights({
  articleId,
  requestSignal = 0,
}: {
  articleId: string;
  /** Bump to start the fetch from outside (e.g. the action bar's Ask button). */
  requestSignal?: number;
}) {
  const insightsMutation = useMutation({
    mutationFn: () => fetchArticleInsights(articleId),
  });
  const { isIdle, mutate } = insightsMutation;

  useEffect(() => {
    if (requestSignal > 0 && isIdle) mutate();
    // Only react to new requests; isIdle/mutate changing must not refire.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestSignal]);

  return (
    <>
      {insightsMutation.isIdle && (
        <button
          onClick={() => insightsMutation.mutate()}
          data-testid="insights-button"
          className="inline-flex min-h-touch items-center gap-1.5 rounded-full border border-border bg-background px-3.5 text-meta font-medium text-muted-foreground transition-colors hover:bg-surface hover:text-foreground md:min-h-9"
        >
          <Sparkles className="size-4" strokeWidth={1.75} />
          Key takeaways
        </button>
      )}
      {insightsMutation.isPending && (
        <div className="w-full basis-full rounded-lg border border-border bg-background px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            <span>Analyzing…</span>
          </div>
        </div>
      )}
      {insightsMutation.isSuccess && insightsMutation.data.length > 0 && (
        <div
          className="w-full basis-full rounded-lg border border-border bg-background px-4 py-3"
          data-testid="insights-section"
        >
          <div className="mb-2 text-xs font-medium uppercase tracking-wider text-subtle">
            Key takeaways
          </div>
          <ul className="space-y-1.5">
            {insightsMutation.data.map((bullet, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-[14px] leading-snug text-foreground"
              >
                <span className="mt-0.5 shrink-0 text-accent">•</span>
                <span>{bullet}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
