import { Link } from 'react-router-dom';
import { Star } from 'lucide-react';
import type { WorkflowArticle } from '@/lib/workflowTypes';
import { relativeTime, signalLabel } from '@/lib/format';
import { cn } from '@/lib/utils';
import { SwipeableRow } from './SwipeableRow';
import { useTriageMutations } from '@/hooks/useTriageMutations';

interface Props {
  article: WorkflowArticle;
  focused?: boolean;
  showLaterUntil?: boolean;
}

export function ArticleRow({ article, focused, showLaterUntil }: Props) {
  const { setState, toggleStar } = useTriageMutations();

  const handleStar = () => toggleStar(article);
  const handleSkip = () => setState(article, 'skipped', 'Skipped');

  const signalColor =
    article.signal === 'high'
      ? 'text-signal-high'
      : article.signal === 'mid'
        ? 'text-signal-mid'
        : 'text-signal-low';

  return (
    <SwipeableRow onSwipeRight={handleStar} onSwipeLeft={handleSkip} disableLeft={article.starred}>
      <Link
        to={`/a/${article.id}`}
        className={cn(
          'motion-fade-up block px-4 py-3 border-b border-border transition-colors hover:bg-surface md:px-5',
          focused && 'bg-surface-2 focus-row'
        )}
      >
        <div className="flex items-baseline justify-between gap-3 mb-1">
          <div className="flex items-baseline gap-1.5 min-w-0 text-[11px] text-muted-foreground">
            <span className="truncate font-medium">{article.sourceName}</span>
            <span>·</span>
            <span className="shrink-0">{relativeTime(article.publishedAt)}</span>
            <span>·</span>
            <span className="truncate">{article.category}</span>
          </div>
          {article.starred && (
            <Star className="size-3.5 shrink-0 fill-star text-star" strokeWidth={1.5} />
          )}
        </div>
        <h3 className="text-[15px] leading-snug font-semibold tracking-tight text-foreground mb-1.5">
          {article.title}
        </h3>
        <p className="text-[13px] leading-snug text-foreground/80 line-clamp-1">{article.reason}</p>
        <div className="mt-1.5 flex items-center gap-2 text-[11px]">
          <span className={cn('font-medium', signalColor)}>{signalLabel(article.signal)}</span>
          {showLaterUntil && article.later_until && (
            <>
              <span className="text-subtle">·</span>
              <span className="text-subtle">returns {relativeTime(article.later_until)}</span>
            </>
          )}
        </div>
      </Link>
    </SwipeableRow>
  );
}
