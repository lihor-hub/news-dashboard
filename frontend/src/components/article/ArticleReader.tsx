import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { fetchArticle, fetchArticleBody, fetchSharedArticle, fetchSharedArticleBody } from '@/api';
import { HttpError } from '@/api/core';
import { adaptArticle, patchArticleState, patchArticleStar } from '@/api/workflowApi';
import type { WorkflowState } from '@/lib/workflowTypes';
import { getOfflineArticle, removeOfflineArticle, saveOfflineArticle } from '@/lib/offline';
import { trackArticleOpen, trackArticleClose } from '@/lib/analytics';
import { cn } from '@/lib/utils';
import { useArticleAudio } from '@/hooks/useArticleAudio';
import { useArticleKeyboardShortcuts } from '@/hooks/useArticleKeyboardShortcuts';
import { useArticleSwipeNav } from '@/hooks/useArticleSwipeNav';
import { useArticleSharing } from '@/hooks/useArticleSharing';
import { ShareDialog } from '@/components/ShareDialog';
import { ArticleHighlights } from '@/components/article/ArticleHighlights';
import { ArticleActionBar } from '@/components/article/ArticleActionBar';
import { ArticleReaderHeader } from '@/components/article/ArticleReaderHeader';
import { ArticleMetaHeader } from '@/components/article/ArticleMetaHeader';
import { ArticleBody } from '@/components/article/ArticleBody';
import { ArticleSelectionActions } from '@/components/article/ArticleSelectionActions';
import { ArticleSummaryCard } from '@/components/article/ArticleSummaryCard';
import { ReadingProgress } from '@/components/article/ReadingProgress';

export type ArticleReaderVariant = 'page' | 'pane';

export interface ArticleReaderProps {
  /** Article to show; ignored when `shareId` is given. */
  articleId?: string;
  /** Share id for read-only shared-article routes. */
  shareId?: string;
  /**
   * `page`: full-screen reader (window scroll, slide-in, floating action bar).
   * `pane`: embedded in a layout (scrolls inside its own box, inline action bar).
   */
  variant?: ArticleReaderVariant;
  /** Back / close. Also bound to Esc. Omit to hide the Back button. */
  onBack?: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  prevId?: string | null;
  nextId?: string | null;
  /** Called after a triage action (done/later/skip/archive/star). Defaults to `onBack`. */
  onActionComplete?: () => void;
  /** Bind the reader's global keyboard shortcuts. Defaults to true. */
  enableShortcuts?: boolean;
  className?: string;
}

function articleErrorCopy(error: unknown) {
  if (error instanceof HttpError && error.status === 404) {
    return {
      title: 'Article not found',
      message: 'This article may have been removed or the shared link is no longer available.',
    };
  }
  return {
    title: 'Could not load article',
    message: 'The article request failed. Check your connection and try again.',
  };
}

const noop = () => undefined;

export function ArticleReader({
  articleId: id,
  shareId,
  variant = 'page',
  onBack,
  onPrev = noop,
  onNext = noop,
  prevId = null,
  nextId = null,
  onActionComplete,
  enableShortcuts = true,
  className,
}: ArticleReaderProps) {
  const queryClient = useQueryClient();
  const isPane = variant === 'pane';
  const scrollRef = useRef<HTMLDivElement>(null);
  const summaryRef = useRef<HTMLElement>(null);
  const articleKey = shareId ? `share:${shareId}` : id;
  const articleQueryKey = useMemo(
    () => (shareId ? ['sharedArticle', shareId] : ['article', id]),
    [id, shareId]
  );

  const {
    data: rawArticle,
    error: articleError,
    isError,
    isLoading,
    isFetching,
    refetch,
  } = useQuery({
    queryKey: articleQueryKey,
    queryFn: () => (shareId ? fetchSharedArticle(shareId) : fetchArticle(id!)),
    enabled: !!articleKey,
    staleTime: 30_000,
  });

  const article = useMemo(() => (rawArticle ? adaptArticle(rawArticle) : null), [rawArticle]);
  const [showOriginal, setShowOriginal] = useState(false);
  const [offlineSavedArticleId, setOfflineSavedArticleId] = useState<string | null>(null);
  const [insightsRequest, setInsightsRequest] = useState(0);

  useEffect(() => {
    setShowOriginal(false);
    setInsightsRequest(0);
    if (isPane) scrollRef.current?.scrollTo?.({ top: 0 });
    if (!id || shareId) {
      setOfflineSavedArticleId(null);
      return;
    }
    setOfflineSavedArticleId(getOfflineArticle(id)?.id ?? null);
  }, [articleKey, id, shareId, isPane]);

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

  const goBack = onBack ?? noop;
  const afterAction = onActionComplete ?? goBack;

  const { swipeDx, touchHandlers } = useArticleSwipeNav(onPrev, onNext);

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
        afterAction();
      } catch {
        toast.error('Action failed');
      }
    },
    [article, queryClient, afterAction]
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
      afterAction();
    } catch {
      toast.error('Action failed');
    }
  }, [article, id, queryClient, afterAction]);

  async function saveCurrentArticleOffline() {
    if (!article) return;
    try {
      const saved = await saveOfflineArticle({
        id: article.id,
        title: article.title,
        source: article.sourceName,
        url: article.url,
      });
      setOfflineSavedArticleId(saved.id);
      toast('Saved for offline');
    } catch {
      toast.error('Could not save offline');
    }
  }

  async function removeCurrentArticleOffline() {
    if (!article) return;
    try {
      await removeOfflineArticle(article.id);
      setOfflineSavedArticleId(null);
      toast('Removed offline save');
    } catch {
      toast.error('Could not remove offline save');
    }
  }

  const handleAsk = useCallback(() => {
    setInsightsRequest((n) => n + 1);
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    summaryRef.current?.scrollIntoView?.({
      behavior: reduceMotion ? 'auto' : 'smooth',
      block: 'start',
    });
  }, []);

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

  // With shortcuts disabled (e.g. a host list owns the keyboard) every handler
  // is inert, so the hook's listener is a no-op.
  useArticleKeyboardShortcuts({
    hasArticle: enableShortcuts && Boolean(article),
    articleUrl: article?.url,
    goBack: enableShortcuts ? goBack : noop,
    goPrev: enableShortcuts ? onPrev : noop,
    goNext: enableShortcuts ? onNext : noop,
    doAction: (state, label) => void doAction(state, label),
    doStar: () => void doStar(),
  });

  const rootClass = cn(
    'bg-background flex flex-col',
    isPane ? 'relative h-full overflow-y-auto overscroll-contain' : 'min-h-screen',
    className
  );

  if (isLoading || isError || !article) {
    const copy = isError ? articleErrorCopy(articleError) : null;
    return (
      <div ref={scrollRef} className={rootClass} data-testid="article-reader">
        <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur">
          <div className="mx-auto flex h-14 max-w-2xl items-center px-2 md:h-12 md:px-3">
            {onBack && (
              <button
                onClick={goBack}
                className="inline-flex min-h-11 items-center gap-1 rounded-md px-2 text-[15px] text-muted-foreground hover:bg-surface hover:text-foreground md:min-h-9 md:text-sm"
              >
                <ArrowLeft className="size-5 rtl:-scale-x-100 md:size-4" /> Back
              </button>
            )}
          </div>
        </header>
        <div className="flex flex-1 items-center justify-center py-16">
          {isLoading ? (
            <Loader2 className="size-5 animate-spin text-muted-foreground motion-reduce:animate-none" />
          ) : copy ? (
            <div role="alert" className="max-w-sm px-5 text-center">
              <p className="text-base font-medium text-foreground">{copy.title}</p>
              <p className="mt-1 text-sm text-muted-foreground">{copy.message}</p>
              {!(articleError instanceof HttpError && articleError.status === 404) ? (
                <button
                  type="button"
                  onClick={() => void refetch()}
                  disabled={isFetching}
                  className="mt-4 inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm font-medium text-foreground hover:bg-surface disabled:opacity-50 md:min-h-9"
                >
                  {isFetching ? 'Retrying...' : 'Retry'}
                </button>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Article not found.</p>
          )}
        </div>
      </div>
    );
  }

  const bodyLoading =
    bodyMutation.isPending || (article.bodyStatus === 'missing' && bodyMutation.isIdle);

  const actionBar = (
    <ArticleActionBar
      layout={isPane ? 'inline' : 'floating'}
      starred={article.starred}
      onStar={() => void doStar()}
      onDone={() => void doAction('done', 'Done')}
      onLater={() => void doAction('later', 'Later')}
      onSkip={() => void doAction('skipped', 'Skipped')}
      onArchive={() => void doAction('archived', 'Archived')}
      onShare={() => void handleShare()}
      onAsk={handleAsk}
      audioState={audioState}
      onListen={handleListen}
    />
  );

  return (
    <div ref={scrollRef} className={rootClass} data-testid="article-reader">
      {/* Header + scrollable content slide in together.  The page action bar is
          portalled out of this wrapper so its position:fixed always resolves
          against the viewport, even while the entry transform is active. */}
      <div className={cn('flex-1 flex flex-col', !isPane && 'motion-slide-in-right')}>
        <ArticleReaderHeader
          goBack={onBack}
          goPrev={onPrev}
          goNext={onNext}
          prevId={prevId}
          nextId={nextId}
          articleUrl={article.url}
          isShared={Boolean(shareId)}
          isSavedOffline={offlineSavedArticleId === String(article.id)}
          onSaveOffline={() => void saveCurrentArticleOffline()}
          onRemoveOffline={() => void removeCurrentArticleOffline()}
          progress={<ReadingProgress containerRef={isPane ? scrollRef : undefined} />}
        />

        {/* Article content */}
        <div
          className={cn('flex-1 overflow-x-hidden', isPane ? 'pb-12' : 'pb-36 md:pb-32')}
          {...(isPane ? {} : touchHandlers)}
        >
          <article
            className="mx-auto max-w-2xl px-5 pt-6 md:pt-10"
            style={
              isPane
                ? undefined
                : {
                    transform: `translateX(${swipeDx * 0.3}px)`,
                    transition: swipeDx ? 'none' : 'transform 0.2s ease',
                  }
            }
          >
            <ArticleMetaHeader
              article={article}
              isShared={Boolean(shareId)}
              showOriginal={showOriginal}
              setShowOriginal={setShowOriginal}
            />

            {isPane && actionBar}

            <ArticleSummaryCard
              ref={summaryRef}
              article={article}
              insightsRequest={insightsRequest}
            />

            <div className="mt-8 md:mt-10">
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

      {!isPane && actionBar}
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
