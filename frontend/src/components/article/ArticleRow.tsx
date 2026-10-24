import { memo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { Star, Info, Siren } from 'lucide-react';
import type { WorkflowArticle } from '@/lib/workflowTypes';
import { relativeTime, signalLabel } from '@/lib/format';
import { recommendationLabel, RECOMMENDATION_LABEL_TEXT } from '@/lib/recommendation';
import { cn } from '@/lib/utils';
import { SwipeableRow } from './SwipeableRow';
import { useTriageMutations } from '@/hooks/useTriageMutations';

interface Props {
  article: WorkflowArticle;
  focused?: boolean;
  showLaterUntil?: boolean;
}

const MAX_ALSO_FROM_SHOWN = 3;
const AVATAR_TONES = 5;

type Tone = 'high' | 'mid' | 'low';

const TONE_TEXT: Record<Tone, string> = {
  high: 'text-signal-high',
  mid: 'text-signal-mid',
  low: 'text-signal-low',
};

const TONE_PILL_BG: Record<Tone, string> = {
  high: 'bg-signal-high/12',
  mid: 'bg-signal-mid/12',
  low: 'bg-signal-low/12',
};

const TONE_BAR: Record<Tone, string> = {
  high: 'bg-signal-high',
  mid: 'bg-signal-mid',
  low: 'bg-signal-low',
};

/** Stable 1-based chart-token index for a source, so its tile colour never shifts. */
function avatarTone(name: string): number {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + (ch.codePointAt(0) ?? 0)) >>> 0;
  return (hash % AVATAR_TONES) + 1;
}

function avatarInitial(name: string): string {
  const first = Array.from(name.trim()).find((ch) => /[\p{L}\p{N}]/u.test(ch));
  return first ? first.toLocaleUpperCase() : '?';
}

function SourceAvatar({ name }: { name: string }) {
  const tone = `var(--color-chart-${avatarTone(name)})`;
  return (
    <span
      aria-hidden="true"
      data-testid="source-avatar"
      className="mt-0.5 grid size-10 shrink-0 place-items-center rounded-xl text-base font-semibold md:size-9 md:text-sm"
      style={{ color: tone, backgroundColor: `color-mix(in oklch, ${tone} 14%, transparent)` }}
    >
      {avatarInitial(name)}
    </span>
  );
}

function ArticleRowComponent({ article, focused, showLaterUntil }: Props) {
  const { t } = useTranslation();
  const { setState, toggleStar } = useTriageMutations();

  const handleDone = () => setState(article, 'done', 'Read');
  const handleSkip = () => setState(article, 'skipped', 'Skipped');
  const handleStar = () => toggleStar(article);

  // Prefer the personalized recommendation band when the article has been ranked
  // for this user; otherwise fall back to the importance-derived visual signal so
  // unranked rows degrade gracefully instead of going blank.
  const recLabel = recommendationLabel(article.recommendationScore);
  const labelText = recLabel ? RECOMMENDATION_LABEL_TEXT[recLabel] : signalLabel(article.signal);
  const tone: Tone =
    recLabel === 'recommended' || (!recLabel && article.signal === 'high')
      ? 'high'
      : recLabel === 'relevant' || (!recLabel && article.signal === 'mid')
        ? 'mid'
        : 'low';
  const score =
    article.recommendationScore != null
      ? Math.min(100, Math.max(0, Math.round(article.recommendationScore)))
      : null;

  const alsoFrom = article.alsoFrom ?? [];
  const alsoCoveredBy =
    alsoFrom.length > 0
      ? t('articleList.alsoCoveredBy', {
          names:
            alsoFrom.slice(0, MAX_ALSO_FROM_SHOWN).join(', ') +
            (alsoFrom.length > MAX_ALSO_FROM_SHOWN
              ? `, ${t('articleList.andMore', { count: alsoFrom.length - MAX_ALSO_FROM_SHOWN })}`
              : ''),
        })
      : null;

  return (
    <div className="content-visibility-auto">
      <SwipeableRow
        onSwipeRight={handleDone}
        onSwipeLeft={handleSkip}
        onLongPress={handleStar}
        disableLeft={article.starred}
        rightLabel={t('articleList.swipeDone')}
        leftLabel={t('articleList.swipeSkip')}
      >
        <Link
          to={`/a/${article.id}`}
          className={cn(
            'motion-fade-up relative flex min-h-12 gap-3 border-b border-border px-4 py-4 transition-colors hover:bg-surface md:px-5 md:py-3',
            article.highPriority &&
              'border-s-4 border-s-[color:var(--err)] bg-[color:color-mix(in_srgb,var(--err)_7%,transparent)]',
            // Logical start-edge bar (RTL-safe) replaces focus-row's physical inset shadow.
            focused &&
              'focus-row bg-accent/8 shadow-none! before:absolute before:inset-y-0 before:start-0 before:w-[3px] before:bg-accent'
          )}
        >
          <SourceAvatar name={article.sourceName} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-1.5 text-[13px] text-muted-foreground md:text-xs">
                <span className="truncate font-medium text-foreground/80">
                  {article.sourceName}
                </span>
                <span aria-hidden="true">·</span>
                <span className="shrink-0">{relativeTime(article.publishedAt)}</span>
                <span aria-hidden="true">·</span>
                <span className="truncate">{article.category}</span>
                {alsoCoveredBy && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span
                      className="shrink-0"
                      data-testid="also-covered-by"
                      title={alsoCoveredBy}
                      aria-label={alsoCoveredBy}
                    >
                      {t('articleList.moreSources', { count: alsoFrom.length })}
                    </span>
                  </>
                )}
                {article.highPriority && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span className="inline-flex shrink-0 items-center gap-1 font-semibold text-[color:var(--err)]">
                      <Siren className="size-4" aria-hidden="true" />
                      {t('priorityFeeds.highPriority')}
                    </span>
                  </>
                )}
                {article.detectedLang && article.detectedLang !== 'en' && article.originalTitle && (
                  <span className="shrink-0 rounded-md border border-border bg-surface px-1.5 text-xs font-medium text-accent">
                    {article.detectedLang.toUpperCase()} → EN
                  </span>
                )}
              </div>
              {article.starred && (
                <Star className="size-4 shrink-0 fill-star text-star" strokeWidth={1.5} />
              )}
            </div>
            <h3 className="mt-1 text-base leading-snug font-semibold tracking-tight text-foreground">
              {article.title}
            </h3>
            <p className="mt-1 text-sm leading-snug text-foreground/75 line-clamp-2 md:line-clamp-1">
              {article.reason}
            </p>
            <div className="mt-2 flex min-h-6 flex-wrap items-center gap-x-2.5 gap-y-1 text-[13px] md:text-xs">
              <span
                className={cn(
                  'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold',
                  TONE_TEXT[tone],
                  TONE_PILL_BG[tone]
                )}
                data-testid="recommendation-label"
                data-source={recLabel ? 'recommendation' : 'signal'}
              >
                {labelText}
              </span>
              {score != null && (
                <span className="inline-flex items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    data-testid="recommendation-match-bar"
                    className="relative h-1 w-14 overflow-hidden rounded-full bg-border"
                  >
                    <span
                      className={cn('absolute inset-y-0 start-0 rounded-full', TONE_BAR[tone])}
                      style={{ width: `${score}%` }}
                    />
                  </span>
                  <span
                    className="text-muted-foreground tabular-nums"
                    data-testid="recommendation-score"
                  >
                    {score}%
                  </span>
                </span>
              )}
              {article.recommendationExplanation && (
                <RecommendationExplanationIcon explanation={article.recommendationExplanation} />
              )}
              {showLaterUntil && article.later_until && (
                <span className="text-subtle">returns {relativeTime(article.later_until)}</span>
              )}
            </div>
          </div>
        </Link>
      </SwipeableRow>
    </div>
  );
}

function RecommendationExplanationIcon({ explanation }: { explanation: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative -my-3 inline-flex items-center">
      <button
        type="button"
        aria-label="Why recommended"
        data-testid="recommendation-explanation-trigger"
        className="grid size-11 place-items-center rounded-full text-muted-foreground/70 transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
      >
        <Info className="size-4" strokeWidth={1.5} aria-hidden="true" />
      </button>
      {open && (
        <span
          role="tooltip"
          data-testid="recommendation-explanation-tooltip"
          // RTL exception: left 50% pairs with translateX(-50%) to center this tooltip.
          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-0.5 z-50 w-56 rounded-md bg-popover border border-border px-2.5 py-1.5 text-xs leading-snug text-popover-foreground shadow-md"
        >
          {explanation}
        </span>
      )}
    </span>
  );
}

export const ArticleRow = memo(ArticleRowComponent);
