import { useState } from 'react';
import { RefreshCw, Sparkles } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { recalculateMyRecommendations } from '@/api';
import { ARTICLES_KEY } from '@/hooks/useTriageMutations';

type RecalcState =
  | { status: 'idle' }
  | { status: 'running' }
  | { status: 'done'; scored: number }
  | { status: 'error' };

export function PersonalizationSection() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<RecalcState>({ status: 'idle' });

  const recalculate = async () => {
    setState({ status: 'running' });
    try {
      const { scored } = await recalculateMyRecommendations();
      setState({ status: 'done', scored });
      // Invalidate cached article data so recommendation scores refresh on next render.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: [ARTICLES_KEY] }),
        queryClient.invalidateQueries({ queryKey: ['article'] }),
      ]);
    } catch {
      setState({ status: 'error' });
    }
  };

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        Personalization
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <p className="text-xs text-muted-foreground">
          Recommendations are learned from articles you star, read, or skip. Refresh to recompute
          your personalized scores now.
        </p>
        <button
          onClick={() => void recalculate()}
          disabled={state.status === 'running'}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
        >
          {state.status === 'running' ? (
            <RefreshCw className="size-3 animate-spin" />
          ) : (
            <Sparkles className="size-3" />
          )}
          {state.status === 'running' ? 'Refreshing…' : 'Refresh recommendations'}
        </button>

        {state.status === 'done' && state.scored > 0 && (
          <p className="text-xs text-green-600 dark:text-green-400">
            Personalized {state.scored} {state.scored === 1 ? 'article' : 'articles'}. Your feed is
            up to date.
          </p>
        )}
        {state.status === 'done' && state.scored === 0 && (
          <p className="text-xs text-muted-foreground">
            Nothing to personalize yet — star, read, or skip a few articles first, then refresh.
          </p>
        )}
        {state.status === 'error' && (
          <p className="text-xs text-destructive">Couldn't refresh recommendations. Try again.</p>
        )}
      </div>
    </section>
  );
}
