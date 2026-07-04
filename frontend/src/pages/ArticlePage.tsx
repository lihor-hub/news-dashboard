import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { fetchArticle, fetchArticleBody, fetchSharedArticle, fetchSharedArticleBody } from '@/api';
import { adaptArticle, patchArticleState, patchArticleStar } from '@/api/workflowApi';
import type { WorkflowState } from '@/lib/workflowTypes';
import { getReaderList } from '@/lib/readerList';
import { cacheArticleBody } from '@/lib/offline';
import { trackArticleOpen, trackArticleClose } from '@/lib/analytics';
import { useArticleAudio } from '@/hooks/useArticleAudio';
import { useArticleKeyboardShortcuts } from '@/hooks/useArticleKeyboardShortcuts';
import { useArticleSwipeNav } from '@/hooks/useArticleSwipeNav';
import { useArticleSharing } from '@/hooks/useArticleSharing';
import { ShareDialog } from '@/components/ShareDialog';
import { ArticleInsights } from '@/components/article/ArticleInsights';
import { ArticlePerspectives } from '@/components/article/ArticlePerspectives';
import { ArticleWhyRecommended } from '@/components/article/ArticleWhyRecommended';
import { ArticleHighlights } from '@/components/article/ArticleHighlights';
import { ArticleActionBar } from '@/components/article/ArticleActionBar';
import { ArticleReaderHeader } from '@/components/article/ArticleReaderHeader';
import { ArticleMetaHeader } from '@/components/article/ArticleMetaHeader';
import { ArticleBody } from '@/components/article/ArticleBody';
import { ArticleSelectionActions } from '@/components/article/ArticleSelectionActions';

export function ArticlePage() {
  const { id, shareId } = useParams<{ id?: string; shareId?: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const articleKey = shareId ? `share:${shareId}` : id;
  const articleQueryKey = useMemo(
    () => (shareId ? ['sharedArticle', shareId] : ['article', id]),
    [id, shareId]
  );

  const { data: rawArticle, isLoading } = useQuery({
    queryKey: articleQueryKey,
    queryFn: () => (shareId ? fetchSharedArticle(shareId) : fetchArticle(id!)),
    enabled: !!articleKey,
    staleTime: 30_000,
  });

  const article = useMemo(() => (rawArticle ? adaptArticle(rawArticle) : null), [rawArticle]);
  const [showOriginal, setShowOriginal] = useState(false);

  useEffect(() => {
    setShowOriginal(false);
  }, [articleKey]);

  // Trigger body fetch in parallel with metadata — fire at mount so we don't
  // wait for the GET /api/articles/:id round-trip before starting the slow scrape.
  const bodyMutation = useMutation({
    mutationFn: () => (shareId ? fetchSharedArticleBody(shareId) : fetchArticleBody(id!)),
    onSuccess: (updated) => {
      queryClient.setQueryData(articleQueryKey, updated);
    },
  });

  useEffect(() => {
    if (!articleKey) return;
    // Skip if the React Query cache already has a fully-fetched body for this article.
    const cached = queryClient.getQueryData<{ body_status?: string }>(articleQueryKey);
    if (cached?.body_status === 'ok') return;
    bodyMutation.mutate();
    // Run once per article id/share id; bodyMutation is intentionally omitted from deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [articleKey]);

  // Per-article dwell telemetry: record an open when the reader mounts (or the
  // user pages to a different article via prev/next, which swaps the id in
  // place) and a close on unmount/id change so the close carries dwell time.
  // This feeds the "Most-read articles" analytics panel via article_close
  // events; without it that panel stays empty.
  useEffect(() => {
    if (!rawArticle) return;
    const articleId = Number(rawArticle.id);
    if (!Number.isFinite(articleId)) return;
    trackArticleOpen(articleId);
    return () => trackArticleClose(articleId);
  }, [rawArticle]);

  // Prev/next navigation from sessionStorage list
  const readerList = getReaderList();
  const idx = readerList && id ? readerList.ids.indexOf(String(id)) : -1;
  const prevId = idx > 0 ? readerList!.ids[idx - 1] : null;
  const nextId =
    idx >= 0 && idx < (readerList?.ids.length ?? 0) - 1 ? readerList!.ids[idx + 1] : null;

  const goBack = useCallback(() => void navigate(-1), [navigate]);
  const goPrev = useCallback(() => {
    if (prevId) void navigate(`/a/${prevId}`, { replace: true });
  }, [navigate, prevId]);
  const goNext = useCallback(() => {
    if (nextId) void navigate(`/a/${nextId}`, { replace: true });
  }, [navigate, nextId]);

  const { swipeDx, touchHandlers } = useArticleSwipeNav(goPrev, goNext);

  // Triage mutations — inline (no extra hook so we stay self-contained)
  const doAction = useCallback(
    async (state: WorkflowState, label: string) => {
      if (!article) return;
      if (state === 'skipped' && article.starred) {
        toast.error("Starred articles can't be skipped");
        return;
      }
      try {
        await patchArticleState(article.id, state, article.starred);
        void queryClient.invalidateQueries({ queryKey: ['articles'] });
        void queryClient.invalidateQueries({ queryKey: ['summary'] });
        toast(label);
        goBack();
      } catch {
        toast.error('Action failed');
      }
    },
    [article, queryClient, goBack]
  );

  const doStar = useCallback(async () => {
    if (!article) return;
    const next = !article.starred;
    try {
      await patchArticleStar(article.id, next);
      void queryClient.invalidateQueries({ queryKey: ['article', id] });
      void queryClient.invalidateQueries({ queryKey: ['articles'] });
      void queryClient.invalidateQueries({ queryKey: ['summary'] });
      toast(next ? 'Starred' : 'Unstarred');
      goBack();
    } catch {
      toast.error('Action failed');
    }
  }, [article, id, queryClient, goBack]);

  async function saveCurrentArticleOffline() {
    if (!article) return;
    try {
      await cacheArticleBody(article.id);
      toast('Saved for offline');
    } catch {
      toast.error('Could not save offline');
    }
  }

  const { audioState, handleListen } = useArticleAudio(id);

  const {
    shareOpen,
    setShareOpen,
    selectedShareText,
    pendingShareHighlight,
    highlights,
    deleteHighlight,
    handleShare,
    updateSelectedShareText,
    handleShareSelected,
    handleHighlightSelected,
  } = useArticleSharing({ id, shareId, article });

  useArticleKeyboardShortcuts({
    hasArticle: Boolean(article),
    articleUrl: article?.url,
    goBack,
    goPrev,
    goNext,
    doAction: (state, label) => void doAction(state, label),
    doStar: () => void doStar(),
  });

  if (isLoading || !article) {
    return (
      <div className="min-h-screen bg-background flex flex-col">
        <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur">
          <div className="mx-auto max-w-2xl flex h-12 items-center px-3">
            <button
              onClick={goBack}
              className="inline-flex items-center gap-1 px-2 py-1 -ml-1 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-surface"
            >
              <ArrowLeft className="size-4" /> Back
            </button>
          </div>
        </header>
        <div className="flex-1 flex items-center justify-center">
          {isLoading ? (
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          ) : (
            <p className="text-sm text-muted-foreground">Article not found.</p>
          )}
        </div>
      </div>
    );
  }

  const bodyLoading =
    bodyMutation.isPending || (article.bodyStatus === 'missing' && bodyMutation.isIdle);

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header + scrollable content slide in together.  The action bar is a
          sibling outside this wrapper so its position:fixed always resolves
          against the viewport, even while the entry transform is active. */}
      <div className="flex-1 flex flex-col motion-slide-in-right">
        <ArticleReaderHeader
          goBack={goBack}
          goPrev={goPrev}
          goNext={goNext}
          prevId={prevId}
          nextId={nextId}
          articleUrl={article.url}
          isShared={Boolean(shareId)}
          onSaveOffline={() => void saveCurrentArticleOffline()}
        />

        {/* Article content */}
        <div className="flex-1 pb-32 overflow-x-hidden" {...touchHandlers}>
          <article
            className="mx-auto max-w-2xl px-5 pt-6"
            style={{
              transform: `translateX(${swipeDx * 0.3}px)`,
              transition: swipeDx ? 'none' : 'transform 0.2s ease',
            }}
          >
            <ArticleMetaHeader
              article={article}
              isShared={Boolean(shareId)}
              showOriginal={showOriginal}
              setShowOriginal={setShowOriginal}
            />

            {/* AI insights — on-demand button → loading → bullet list */}
            <ArticleInsights articleId={String(article.id)} />

            {/* Context & Perspectives — on-demand AI fact-check widget */}
            <ArticlePerspectives articleId={String(article.id)} />

            {/* Why this matters */}
            <div className="mt-4 rounded-lg border-l-2 border-accent bg-surface/60 px-4 py-3">
              <div className="text-[10px] font-medium uppercase tracking-wider text-subtle mb-1">
                Why this matters
              </div>
              <p className="text-[14px] leading-snug text-foreground">{article.reason}</p>
            </div>

            {/* Why recommended — on-demand explanation of the personalized ranking */}
            <ArticleWhyRecommended
              aiExplanation={article.recommendationExplanation}
              score={article.recommendationScore}
              signals={article.recommendationSignals}
            />

            <div className="mt-8">
              <ArticleBody
                article={article}
                bodyLoading={bodyLoading}
                showOriginal={showOriginal}
                onSelectText={updateSelectedShareText}
              />
            </div>

            {!shareId && <ArticleHighlights highlights={highlights} onDelete={deleteHighlight} />}
          </article>
        </div>
      </div>
      {/* end animated wrapper */}

      <ArticleActionBar
        starred={article.starred}
        onStar={() => void doStar()}
        onDone={() => void doAction('done', 'Done')}
        onLater={() => void doAction('later', 'Later')}
        onSkip={() => void doAction('skipped', 'Skipped')}
        onArchive={() => void doAction('archived', 'Archived')}
        onShare={() => void handleShare()}
        audioState={audioState}
        onListen={handleListen}
      />
      <ArticleSelectionActions
        selectedText={selectedShareText}
        isShared={Boolean(shareId)}
        onHighlight={handleHighlightSelected}
        onShare={handleShareSelected}
      />
      <ShareDialog
        open={shareOpen}
        onOpenChange={setShareOpen}
        article={{ id: Number(article.id), title: article.title, url: article.url }}
        pendingHighlight={pendingShareHighlight}
      />
    </div>
  );
}
