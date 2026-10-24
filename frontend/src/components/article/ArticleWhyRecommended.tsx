import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, Lightbulb } from 'lucide-react';
import { AiFeedbackThumbs } from '@/components/AiFeedbackThumbs';
import { recommendationExplanation } from '@/lib/recommendation';
import { cn } from '@/lib/utils';
import type { RecommendationSignals } from '@/lib/workflowTypes';

export function ArticleWhyRecommended({
  articleId,
  aiExplanation,
  score,
  signals,
}: {
  articleId: number;
  aiExplanation: string | null | undefined;
  score: number | null | undefined;
  signals: RecommendationSignals | null | undefined;
}) {
  const { t } = useTranslation();
  const [showWhyRecommended, setShowWhyRecommended] = useState(false);
  const explanation = recommendationExplanation({ score, signals });
  // The strongest reason stays visible inline; the full breakdown is on demand.
  const headline = aiExplanation || explanation.reasons[0];

  return (
    <div className="mt-3">
      {!showWhyRecommended && headline && (
        <p
          className="flex items-start gap-2 text-[14px] leading-snug text-foreground"
          data-testid="why-recommended-inline"
        >
          <Lightbulb className="mt-0.5 size-4 shrink-0 text-accent" strokeWidth={1.75} />
          <span className="line-clamp-2">
            <span className="font-medium">{t('reader.why_for_you', 'Why for you')}:</span>{' '}
            {headline}
          </span>
        </p>
      )}
      {showWhyRecommended && (
        <div data-testid="why-recommended-section">
          <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-subtle">
            <Lightbulb className="size-4 text-accent" strokeWidth={1.75} />
            {t('reader.why_for_you', 'Why for you')}
          </div>
          {aiExplanation ? (
            <p
              className="text-[14px] leading-snug text-foreground"
              data-testid="why-recommended-ai-explanation"
            >
              {aiExplanation}
            </p>
          ) : (
            <ul className="space-y-1.5">
              {explanation.reasons.map((reason, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 text-[14px] leading-snug text-foreground"
                >
                  <span className="mt-0.5 shrink-0 text-accent">•</span>
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <div className="mt-1 flex items-center gap-1 ps-5">
        <button
          type="button"
          onClick={() => setShowWhyRecommended((v) => !v)}
          data-testid="why-recommended-button"
          aria-expanded={showWhyRecommended}
          className="-ms-2 inline-flex min-h-touch items-center gap-1 rounded-md px-2 text-meta font-medium text-muted-foreground transition-colors hover:bg-surface hover:text-foreground md:min-h-8"
        >
          {showWhyRecommended
            ? t('reader.why_hide', 'Hide details')
            : t('reader.why_details', 'Why recommended?')}
          <ChevronDown
            className={cn(
              'size-4 transition-transform motion-reduce:transition-none',
              showWhyRecommended && 'rotate-180'
            )}
            strokeWidth={1.75}
          />
        </button>
        <AiFeedbackThumbs subjectType="recommendation" subjectId={articleId} />
      </div>
    </div>
  );
}
