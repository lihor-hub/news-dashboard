import { useMutation } from '@tanstack/react-query';
import { Loader2, Sparkles } from 'lucide-react';
import { fetchArticleInsights } from '@/api';

export function ArticleInsights({ articleId }: { articleId: string }) {
  const insightsMutation = useMutation({
    mutationFn: () => fetchArticleInsights(articleId),
  });

  return (
    <>
      {insightsMutation.isIdle && (
        <button
          onClick={() => insightsMutation.mutate()}
          data-testid="insights-button"
          className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-border bg-surface/40 px-3 py-1.5 text-[12px] font-medium text-muted-foreground hover:text-foreground hover:bg-surface transition-colors"
        >
          <Sparkles className="size-3.5" strokeWidth={1.75} />
          Key takeaways
        </button>
      )}
      {insightsMutation.isPending && (
        <div className="mt-4 rounded-lg border border-border bg-surface/40 px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            <span>Analyzing…</span>
          </div>
        </div>
      )}
      {insightsMutation.isSuccess && insightsMutation.data.length > 0 && (
        <div
          className="mt-4 rounded-lg border border-border bg-surface/40 px-4 py-3"
          data-testid="insights-section"
        >
          <div className="text-[10px] font-medium uppercase tracking-wider text-subtle mb-2">
            Key takeaways
          </div>
          <ul className="space-y-1.5">
            {insightsMutation.data.map((bullet, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-[13px] leading-snug text-foreground"
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
