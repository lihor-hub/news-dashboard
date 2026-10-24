import { useId, type Ref } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import type { WorkflowArticle } from '@/lib/workflowTypes';
import { ArticleInsights } from '@/components/article/ArticleInsights';
import { ArticlePerspectives } from '@/components/article/ArticlePerspectives';
import { ArticleWhyRecommended } from '@/components/article/ArticleWhyRecommended';

/**
 * "In 30 seconds" card shown above the body: AI summary, why it matters, the
 * inline "why for you" reason, and the on-demand AI tools.
 */
export function ArticleSummaryCard({
  article,
  insightsRequest,
  ref,
}: {
  article: WorkflowArticle;
  insightsRequest: number;
  ref?: Ref<HTMLElement>;
}) {
  const { t } = useTranslation();
  const headingId = useId();

  return (
    <section
      ref={ref}
      aria-labelledby={headingId}
      data-testid="summary-card"
      className="mt-6 scroll-mt-28 rounded-xl border border-border bg-surface/60 px-4 py-4 md:px-5"
    >
      <h2
        id={headingId}
        className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-accent"
      >
        <Sparkles className="size-4" strokeWidth={1.75} />
        {t('reader.summary_title', 'In 30 seconds')}
      </h2>

      {article.summary && (
        <p className="mt-2 text-[15px] leading-relaxed text-foreground md:text-base">
          {article.summary}
        </p>
      )}

      {article.reason && (
        <p className="mt-3 border-s-2 border-accent ps-3 text-[14px] leading-snug text-foreground">
          <span className="block text-xs font-medium uppercase tracking-wider text-subtle">
            {t('reader.why_matters', 'Why this matters')}
          </span>
          {article.reason}
        </p>
      )}

      <ArticleWhyRecommended
        articleId={Number(article.id)}
        aiExplanation={article.recommendationExplanation}
        score={article.recommendationScore}
        signals={article.recommendationSignals}
      />

      <div className="mt-3 flex flex-wrap gap-2 border-t border-border pt-3">
        <ArticleInsights articleId={String(article.id)} requestSignal={insightsRequest} />
        <ArticlePerspectives articleId={String(article.id)} />
      </div>
    </section>
  );
}
