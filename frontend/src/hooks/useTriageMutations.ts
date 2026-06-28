import { useQueryClient, useMutation, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';

// Single shared ID so every triage toast replaces the previous one rather than
// stacking — rapid actions (read, skip, star) should show only the latest.
const TRIAGE_TOAST_ID = 'triage';
import { trackFeature } from '../lib/analytics';
import type { WorkflowArticle, WorkflowState } from '../lib/workflowTypes';
import {
  patchArticleState,
  patchArticleStar,
  patchArticleLater,
  snapshot,
} from '../api/workflowApi';

// ─── Query key helpers ───────────────────────────────────────────────────────

export const ARTICLES_KEY = 'articles';

interface ArticleQuerySnapshot {
  queryKey: QueryKey;
  articles: WorkflowArticle[];
}

function articleMatchesQuery(queryKey: QueryKey, article: WorkflowArticle) {
  const [, view] = queryKey;
  if (view === 'today' || view === 'later' || view === 'archived') {
    return article.state === view;
  }
  if (view === 'starred') {
    return article.starred;
  }
  if (view && typeof view === 'object' && !Array.isArray(view)) {
    const filters = view as { state?: WorkflowState; starred?: boolean };
    if (filters.state && article.state !== filters.state) return false;
    if (filters.starred === true && !article.starred) return false;
  }
  return true;
}

function snapshotArticleQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  id: string
): ArticleQuerySnapshot[] {
  return queryClient
    .getQueriesData<WorkflowArticle[]>({ queryKey: [ARTICLES_KEY] })
    .flatMap(([queryKey, articles]) => {
      if (!articles?.some((article) => article.id === id)) return [];
      return [{ queryKey, articles: [...articles] }];
    });
}

function restoreQuerySnapshots(
  queryClient: ReturnType<typeof useQueryClient>,
  snapshots: ArticleQuerySnapshot[]
) {
  snapshots.forEach(({ queryKey, articles }) => {
    queryClient.setQueryData(queryKey, articles);
  });
}

function applyPatchToCache(
  queryClient: ReturnType<typeof useQueryClient>,
  id: string,
  patch: Partial<WorkflowArticle>
) {
  queryClient
    .getQueriesData<WorkflowArticle[]>({ queryKey: [ARTICLES_KEY] })
    .forEach(([queryKey, old]) => {
      if (!old) return;
      let changed = false;
      const next = old.flatMap((article) => {
        if (article.id !== id) return [article];
        changed = true;
        const patched = { ...article, ...patch };
        return articleMatchesQuery(queryKey, patched) ? [patched] : [];
      });
      if (changed) queryClient.setQueryData(queryKey, next);
    });
}

function restoreToCache(queryClient: ReturnType<typeof useQueryClient>, article: WorkflowArticle) {
  queryClient.setQueriesData({ queryKey: [ARTICLES_KEY] }, (old: WorkflowArticle[] | undefined) => {
    if (!old) return old;
    return old.map((a) => (a.id === article.id ? article : a));
  });
}

/**
 * Settle the caches after a triage action resolves (success, error, or undo).
 *
 * The optimistic `applyPatchToCache`/`restoreQuerySnapshots` already left every
 * state-filtered article list correct, and the triage endpoints (`/state`,
 * `/star`, `/later`) have no cross-article side effects — so refetching the full
 * article list on every click only adds a network round-trip and risks a
 * flicker/reorder on a remote backend. Mark the lists stale *without* an
 * immediate refetch (they refresh lazily on the next mount) and only refetch the
 * cheap summary counts, which aren't derivable from the cache.
 */
function settleArticleCaches(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: [ARTICLES_KEY], refetchType: 'none' });
  void queryClient.invalidateQueries({ queryKey: ['summary'] });
}

function triageErrorMessage(err: unknown): string {
  const detail = err instanceof Error && err.message ? err.message : null;
  return detail
    ? `Action failed — ${detail}. Changes reverted.`
    : 'Action failed — changes reverted';
}

// ─── Hook ───────────────────────────────────────────────────────────────────

export function useTriageMutations() {
  const queryClient = useQueryClient();

  const setStateMutation = useMutation({
    mutationFn: ({ article, newState }: { article: WorkflowArticle; newState: WorkflowState }) =>
      patchArticleState(article.id, newState, article.starred),

    onMutate: ({ article, newState }) => {
      void queryClient.cancelQueries({ queryKey: [ARTICLES_KEY] });
      const snap = snapshot(article);
      const querySnapshots = snapshotArticleQueries(queryClient, article.id);
      const now = new Date().toISOString();
      const patch: Partial<WorkflowArticle> = { state: newState };
      if (newState === 'done') patch.done_at = now;
      if (newState === 'skipped') patch.skipped_at = now;
      if (newState === 'archived') patch.archived_at = now;
      if (newState === 'today') {
        patch.restored_at = now;
        patch.later_until = undefined;
      }
      applyPatchToCache(queryClient, article.id, patch);
      return { snap, querySnapshots };
    },

    onError: (err, _vars, context) => {
      if (context?.querySnapshots) restoreQuerySnapshots(queryClient, context.querySnapshots);
      else if (context?.snap) restoreToCache(queryClient, context.snap.article);
      toast.error(triageErrorMessage(err), { id: TRIAGE_TOAST_ID });
    },

    onSettled: () => {
      settleArticleCaches(queryClient);
    },
  });

  const starMutation = useMutation({
    mutationFn: ({ article, starred }: { article: WorkflowArticle; starred: boolean }) =>
      patchArticleStar(article.id, starred),

    onMutate: ({ article, starred }) => {
      void queryClient.cancelQueries({ queryKey: [ARTICLES_KEY] });
      const snap = snapshot(article);
      const querySnapshots = snapshotArticleQueries(queryClient, article.id);
      applyPatchToCache(queryClient, article.id, {
        starred,
        starred_at: starred ? new Date().toISOString() : article.starred_at,
      });
      return { snap, querySnapshots };
    },

    onError: (err, _vars, context) => {
      if (context?.querySnapshots) restoreQuerySnapshots(queryClient, context.querySnapshots);
      else if (context?.snap) restoreToCache(queryClient, context.snap.article);
      toast.error(triageErrorMessage(err), { id: TRIAGE_TOAST_ID });
    },

    onSettled: () => {
      settleArticleCaches(queryClient);
    },
  });

  const sendLaterMutation = useMutation({
    mutationFn: async ({ article, days = 1 }: { article: WorkflowArticle; days?: number }) => {
      await patchArticleLater(article.id, days);
    },

    onMutate: ({ article, days = 1 }) => {
      void queryClient.cancelQueries({ queryKey: [ARTICLES_KEY] });
      const snap = snapshot(article);
      const querySnapshots = snapshotArticleQueries(queryClient, article.id);
      const until = new Date(Date.now() + days * 24 * 3600 * 1000).toISOString();
      applyPatchToCache(queryClient, article.id, { state: 'later', later_until: until });
      return { snap, querySnapshots };
    },

    onError: (err, _vars, context) => {
      if (context?.querySnapshots) restoreQuerySnapshots(queryClient, context.querySnapshots);
      else if (context?.snap) restoreToCache(queryClient, context.snap.article);
      toast.error(triageErrorMessage(err), { id: TRIAGE_TOAST_ID });
    },

    onSettled: () => {
      settleArticleCaches(queryClient);
    },
  });

  function setState(article: WorkflowArticle, newState: WorkflowState, label: string) {
    if (newState === 'skipped' && article.starred) {
      toast.error("Starred articles can't be skipped", { id: TRIAGE_TOAST_ID });
      return;
    }
    const snap = snapshot(article);
    const querySnapshots = snapshotArticleQueries(queryClient, article.id);
    trackFeature(`triage_${newState}`);
    setStateMutation.mutate({ article, newState });
    toast(label, {
      id: TRIAGE_TOAST_ID,
      action: {
        label: 'Undo',
        onClick: () => {
          restoreQuerySnapshots(queryClient, querySnapshots);
          void patchArticleState(snap.article.id, snap.article.state, snap.article.starred).then(
            () => {
              settleArticleCaches(queryClient);
            }
          );
        },
      },
    });
  }

  function toggleStar(article: WorkflowArticle) {
    const nextStarred = !article.starred;
    const snap = snapshot(article);
    const querySnapshots = snapshotArticleQueries(queryClient, article.id);
    trackFeature(nextStarred ? 'star' : 'unstar');
    starMutation.mutate({ article, starred: nextStarred });
    toast(nextStarred ? 'Starred' : 'Unstarred', {
      id: TRIAGE_TOAST_ID,
      action: {
        label: 'Undo',
        onClick: () => {
          restoreQuerySnapshots(queryClient, querySnapshots);
          void patchArticleStar(snap.article.id, snap.article.starred).then(() => {
            settleArticleCaches(queryClient);
          });
        },
      },
    });
  }

  function sendLater(article: WorkflowArticle, days = 1) {
    const snap = snapshot(article);
    const querySnapshots = snapshotArticleQueries(queryClient, article.id);
    trackFeature('snooze');
    sendLaterMutation.mutate({ article, days });
    toast('Snoozed to tomorrow', {
      id: TRIAGE_TOAST_ID,
      action: {
        label: 'Undo',
        onClick: () => {
          restoreQuerySnapshots(queryClient, querySnapshots);
          void patchArticleState(snap.article.id, snap.article.state, snap.article.starred).then(
            () => {
              settleArticleCaches(queryClient);
            }
          );
        },
      },
    });
  }

  return { setState, toggleStar, sendLater };
}
