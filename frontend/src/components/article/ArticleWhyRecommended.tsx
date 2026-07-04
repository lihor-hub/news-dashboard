import { useState } from 'react';
import { Lightbulb } from 'lucide-react';
import { recommendationExplanation } from '@/lib/recommendation';
import type { RecommendationSignals } from '@/lib/workflowTypes';

export function ArticleWhyRecommended({
  aiExplanation,
  score,
  signals,
}: {
  aiExplanation: string | null | undefined;
  score: number | null | undefined;
  signals: RecommendationSignals | null | undefined;
}) {
  const [showWhyRecommended, setShowWhyRecommended] = useState(false);

  return (
    <div className="mt-3">
      <button
        onClick={() => setShowWhyRecommended((v) => !v)}
        data-testid="why-recommended-button"
        aria-expanded={showWhyRecommended}
        className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface/40 px-3 py-1.5 text-[12px] font-medium text-muted-foreground hover:text-foreground hover:bg-surface transition-colors"
      >
        <Lightbulb className="size-3.5" strokeWidth={1.75} />
        {showWhyRecommended ? 'Hide why recommended' : 'Why recommended?'}
      </button>
      {showWhyRecommended &&
        (() => {
          const explanation = recommendationExplanation({ score, signals });
          return (
            <div
              className="mt-2 rounded-lg border border-border bg-surface/40 px-4 py-3"
              data-testid="why-recommended-section"
            >
              <div className="text-[10px] font-medium uppercase tracking-wider text-subtle mb-2">
                Why recommended
              </div>
              {aiExplanation ? (
                <p
                  className="text-[13px] leading-snug text-foreground"
                  data-testid="why-recommended-ai-explanation"
                >
                  {aiExplanation}
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {explanation.reasons.map((reason, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 text-[13px] leading-snug text-foreground"
                    >
                      <span className="mt-0.5 shrink-0 text-accent">•</span>
                      <span>{reason}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })()}
    </div>
  );
}
