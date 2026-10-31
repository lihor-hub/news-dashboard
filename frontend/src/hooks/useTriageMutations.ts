import {
  useQueryClient,
  useMutation,
  type QueryKey,
  type InfiniteData,
} from '@tanstack/react-query';
import { toast } from 'sonner';
import { privateSessionRevision } from '../lib/privateSession';

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
  type TriageArticlePage,
} from '../api/workflowApi';

// ─── Query key helpers ───────────────────────────────────────────────────────

export const ARTICLES_KEY = 'articles';

// Article lists are loaded with `useInfiniteQuery`, so the cached value is an
// `InfiniteData` page envelope — not a flat `WorkflowArticle[]`. All cache reads
// and optimistic writes below operate through the `pages` structure.
type ArticleListCache = InfiniteData<TriageArticlePage>;
type UndoIntent = { requested: boolean; revision: number };

interface ArticleQuerySnapshot {
  queryKey: QueryKey;
  data: ArticleListCache;
  articleId: string;
  revision: number;
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

function cacheContainsArticle(data: ArticleListCache | undefined, id: string): boolean {
  return Boolean(data?.pages.some((page) => page.items.some((article) => article.id === id)));
}

function snapshotArticleQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  id: string
): ArticleQuerySnapshot[] {
  return queryClient
    .getQueriesData<ArticleListCache>({ queryKey: [ARTICLES_KEY] })
    .flatMap(([queryKey, data]) => {
      if (!data || !cacheContainsArticle(data, id)) return [];
      return [{ queryKey, data, articleId: id, revision: privateSessionRevision() }];
    });
}

function restoreQuerySnapshots(
  queryClient: ReturnType<typeof useQueryClient>,
  snapshots: ArticleQuerySnapshot[]
) {
  snapshots.forEach(({ queryKey, data, articleId, revision }) => {
    if (revision !== privateSessionRevision()) return;
    queryClient.setQueryData<ArticleListCache>(queryKey, (current) => {
      if (!current) return current;
      // Roll back only this article. Restoring a whole list resurrects other
      // articles removed by a later click (or by another mounted hook).
      return {
        ...current,
        pages: current.pages.map((page, pageIndex) => {
          const originalItems = data.pages[pageIndex]?.items ?? [];
          const originalIndex = originalItems.findIndex((article) => article.id === articleId);
          const items = page.items.filter((article) => article.id !== articleId);
          if (originalIndex !== -1) {
            // Use a surviving neighbour as the insertion anchor, since earlier
            // articles may also have been optimistically removed.
            const following = originalItems.slice(originalIndex + 1);
            const anchor = items.findIndex((article) => following.some((a) => a.id === article.id));
            items.splice(anchor === -1 ? items.length : anchor, 0, originalItems[originalIndex]);
          }
          return { ...page, items };
        }),
      };
    });
  });
}

function applyPatchToCache(
  queryClient: ReturnType<typeof useQueryClient>,
  id: string,
  patch: Partial<WorkflowArticle>
) {
  queryClient
    .getQueriesData<ArticleListCache>({ queryKey: [ARTICLES_KEY] })
    .forEach(([queryKey, old]) => {
      if (!old) return;
      let changed = false;
      const pages = old.pages.map((page) => {
        const items = page.items.flatMap((article) => {
          if (article.id !== id) return [article];
          changed = true;
          const patched = { ...article, ...patch };
          return articleMatchesQuery(queryKey, patched) ? [patched] : [];
        });
        return { ...page, items };
      });
      if (changed) queryClient.setQueryData<ArticleListCache>(queryKey, { ...old, pages });
    });
}

function restoreToCache(queryClient: ReturnType<typeof useQueryClient>, article: WorkflowArticle) {
  queryClient.setQueriesData<ArticleListCache>(
    { queryKey: [ARTICLES_KEY] },
    (old: ArticleListCache | undefined) => {
      if (!old) return old;
      return {
        ...old,
        pages: old.pages.map((page) => ({
          ...page,
          items: page.items.map((a) => (a.id === article.id ? article : a)),
        })),
      };
    }
  );
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
  void queryClient.invalidateQueries({ queryKey: ['progress-rewards'] });
  void queryClient.invalidateQueries({ queryKey: ['achievements'] });
  void queryClient.invalidateQueries({ queryKey: [ARTICLES_KEY], refetchType: 'none' });
  void queryClient.invalidateQueries({ queryKey: ['article'], refetchType: 'none' });
  // One counts refresh per burst; an earlier response must not expose counts
  // that predate still-pending optimistic removals.
  if (queryClient.isMutating({ mutationKey: ['triage'] }) <= 1) {
    void queryClient.invalidateQueries({ queryKey: ['summary'] });
  }
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
    mutationKey: ['triage'],
    mutationFn: ({
      article,
      newState,
    }: {
      article: WorkflowArticle;
      newState: WorkflowState;
      undo?: UndoIntent;
    }) => patchArticleState(article.id, newState, article.starred),

    onMutate: ({ article, newState, undo }) => {
      if (undo && undo.revision !== privateSessionRevision()) throw new Error('Session changed');
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
      if (!undo?.requested) applyPatchToCache(queryClient, article.id, patch);
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
    mutationKey: ['triage'],
    mutationFn: ({
      article,
      starred,
    }: {
      article: WorkflowArticle;
      starred: boolean;
      undo?: UndoIntent;
    }) => patchArticleStar(article.id, starred),

    onMutate: ({ article, starred, undo }) => {
      if (undo && undo.revision !== privateSessionRevision()) throw new Error('Session changed');
      void queryClient.cancelQueries({ queryKey: [ARTICLES_KEY] });
      const snap = snapshot(article);
      const querySnapshots = snapshotArticleQueries(queryClient, article.id);
      if (!undo?.requested)
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
    mutationKey: ['triage'],
    mutationFn: async ({
      article,
      days = 1,
    }: {
      article: WorkflowArticle;
      days?: number;
      undo?: UndoIntent;
    }) => {
      await patchArticleLater(article.id, days);
    },

    onMutate: ({ article, days = 1, undo }) => {
      if (undo && undo.revision !== privateSessionRevision()) throw new Error('Session changed');
      void queryClient.cancelQueries({ queryKey: [ARTICLES_KEY] });
      const snap = snapshot(article);
      const querySnapshots = snapshotArticleQueries(queryClient, article.id);
      const until = new Date(Date.now() + days * 24 * 3600 * 1000).toISOString();
      if (!undo?.requested)
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
    const undo = { requested: false, revision: privateSessionRevision() };
    const pending = setStateMutation
      .mutateAsync({ article, newState, undo })
      .catch(() => undefined);
    toast(label, {
      id: TRIAGE_TOAST_ID,
      action: {
        label: 'Undo',
        onClick: () => {
          if (undo.revision !== privateSessionRevision()) return;
          restoreQuerySnapshots(queryClient, querySnapshots);
          undo.requested = true;
          undoAfter(pending, () =>
            patchArticleState(snap.article.id, snap.article.state, snap.article.starred)
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
    const undo = { requested: false, revision: privateSessionRevision() };
    const pending = starMutation
      .mutateAsync({ article, starred: nextStarred, undo })
      .catch(() => undefined);
    toast(nextStarred ? 'Starred' : 'Unstarred', {
      id: TRIAGE_TOAST_ID,
      action: {
        label: 'Undo',
        onClick: () => {
          if (undo.revision !== privateSessionRevision()) return;
          restoreQuerySnapshots(queryClient, querySnapshots);
          undo.requested = true;
          undoAfter(pending, () => patchArticleStar(snap.article.id, snap.article.starred));
        },
      },
    });
  }

  function sendLater(article: WorkflowArticle, days = 1) {
    const snap = snapshot(article);
    const querySnapshots = snapshotArticleQueries(queryClient, article.id);
    trackFeature('snooze');
    const undo = { requested: false, revision: privateSessionRevision() };
    const pending = sendLaterMutation.mutateAsync({ article, days, undo }).catch(() => undefined);
    toast('Snoozed to tomorrow', {
      id: TRIAGE_TOAST_ID,
      action: {
        label: 'Undo',
        onClick: () => {
          if (undo.revision !== privateSessionRevision()) return;
          restoreQuerySnapshots(queryClient, querySnapshots);
          undo.requested = true;
          undoAfter(pending, () =>
            patchArticleState(snap.article.id, snap.article.state, snap.article.starred)
          );
        },
      },
    });
  }

  function undoAfter(pending: Promise<unknown>, revert: () => Promise<void>) {
    const revision = privateSessionRevision();
    // Undo is immediately visible, but its write must follow the original write
    // on the server, even when the user clicks before that request has started.
    void pending
      .then(() => {
        if (revision === privateSessionRevision()) return revert();
      })
      .then(() => settleArticleCaches(queryClient))
      .catch((err) => {
        toast.error(`Undo failed — ${err instanceof Error ? err.message : 'please retry'}`, {
          id: TRIAGE_TOAST_ID,
        });
        void queryClient.invalidateQueries({ queryKey: [ARTICLES_KEY] });
        void queryClient.invalidateQueries({ queryKey: ['article'] });
      });
  }

  return { setState, toggleStar, sendLater };
}
