import { useCallback, useEffect, useMemo, useRef } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router';
import { useInfiniteQuery, type QueryKey } from '@tanstack/react-query';
import { BookOpen, Headphones } from 'lucide-react';
import { ArticleReader } from '@/components/article/ArticleReader';
import { ArticleRow } from '@/components/article/ArticleRow';
import { SplitPaneLayout } from '@/components/layout/SplitPaneLayout';
import { SwipeHint } from '@/components/article/SwipeableRow';
import { CategoryFilter } from '@/components/CategoryFilter';
import { EmptyState, type EmptyStateProps } from '@/components/EmptyState';
import { InlineError, ListSkeleton, RetryableErrorState } from '@/components/PageState';
import { useFocusedArticle } from '@/contexts/focusedArticle';
import { useListenQueue } from '@/contexts/listenQueue';
import { useArticleListNav } from '@/hooks/useArticleListNav';
import { DESKTOP_SPLIT_QUERY, useMediaQuery } from '@/hooks/useMediaQuery';
import { useTriageMutations } from '@/hooks/useTriageMutations';
import { setReaderList } from '@/lib/readerList';
import type { WorkflowArticle } from '@/lib/workflowTypes';
import type { TriageArticlePage } from '@/api/workflowApi';

const ARTICLE_PAGE_SIZE = 100;
/** Search param holding the article shown in the desktop reading pane. */
export const SELECTED_ARTICLE_PARAM = 'a';

interface ArticleListViewProps {
  title: string;
  description: (state: {
    count: number;
    loadedCount: number;
    hasMore: boolean;
    isLoading: boolean;
  }) => ReactNode;
  queryKey: QueryKey;
  queryFn: (params: { limit: number; offset: number }) => Promise<TriageArticlePage>;
  empty: EmptyStateProps;
  /** Custom empty view (e.g. Today's caught-up state); overrides `empty` when set. */
  emptyContent?: ReactNode;
  showCategoryFilter?: boolean;
  showLaterUntil?: boolean;
  sortArticles?: (articles: WorkflowArticle[]) => WorkflowArticle[];
  banner?: ReactNode;
  action?: (state: { articles: WorkflowArticle[] }) => ReactNode;
  /** Desktop reading pane: select the first article when nothing is selected. */
  autoSelectFirst?: boolean;
}

export function ArticleListView({
  title,
  description,
  queryKey,
  queryFn,
  empty,
  emptyContent,
  showCategoryFilter,
  showLaterUntil,
  sortArticles,
  banner,
  action,
  autoSelectFirst = false,
}: ArticleListViewProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const isDesktop = useMediaQuery(DESKTOP_SPLIT_QUERY);
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetching,
    isFetchingNextPage,
    isLoading,
    isError,
    isFetchNextPageError,
    refetch,
  } = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) => queryFn({ limit: ARTICLE_PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage) =>
      lastPage.hasMore ? lastPage.offset + lastPage.items.length : undefined,
  });
  const articles = useMemo(() => data?.pages.flatMap((page) => page.items) ?? [], [data?.pages]);
  const hasMore = Boolean(hasNextPage);

  const list = useMemo(
    () => (sortArticles ? sortArticles(articles) : articles),
    [articles, sortArticles]
  );

  useEffect(() => {
    setReaderList(list.map((article) => article.id));
  }, [list]);

  const { start: startListenQueue } = useListenQueue();
  const mutations = useTriageMutations();

  // Desktop reading pane: the selection lives in `?a=<id>` so links, reloads
  // and the back button keep working. Below lg rows open the full page.
  const selectedId = isDesktop ? searchParams.get(SELECTED_ARTICLE_PARAM) : null;
  const selectedIndex = selectedId ? list.findIndex((article) => article.id === selectedId) : -1;
  const split = isDesktop && (isLoading || list.length > 0 || selectedId != null);

  const selectionHref = useCallback(
    (id: string | null) => {
      const next = new URLSearchParams(searchParams);
      if (id) next.set(SELECTED_ARTICLE_PARAM, id);
      else next.delete(SELECTED_ARTICLE_PARAM);
      const query = next.toString();
      return query ? `?${query}` : '';
    },
    [searchParams]
  );
  const select = useCallback(
    (id: string | null) => {
      // Keyboard stepping replaces the entry so Back leaves the list, not the step.
      setSearchParams(new URLSearchParams(selectionHref(id)), { replace: true });
    },
    [selectionHref, setSearchParams]
  );
  const clearSelection = useCallback(() => select(null), [select]);
  const selectIndex = useCallback(
    (index: number) => select(list[index]?.id ?? null),
    [list, select]
  );

  // When the selected article leaves the list (triaged in the pane or via a
  // shortcut), move on to whatever now sits in its slot.
  const lastSelectedIndex = useRef(-1);
  useEffect(() => {
    if (!split || !selectedId) {
      lastSelectedIndex.current = -1;
      return;
    }
    if (selectedIndex >= 0) {
      lastSelectedIndex.current = selectedIndex;
      return;
    }
    if (lastSelectedIndex.current < 0 || isFetching) return;
    const fallback = list[Math.min(lastSelectedIndex.current, list.length - 1)];
    lastSelectedIndex.current = -1;
    select(fallback?.id ?? null);
  }, [split, selectedId, selectedIndex, list, isFetching, select]);

  useEffect(() => {
    if (split && autoSelectFirst && !selectedId && list[0]) select(list[0].id);
  }, [split, autoSelectFirst, selectedId, list, select]);

  const { focused } = useArticleListNav(
    list,
    (article) => void navigate(`/a/${article.id}`),
    mutations,
    split ? { focused: selectedIndex, onFocusChange: selectIndex, onEscape: clearSelection } : {}
  );
  const { set: setFocused } = useFocusedArticle();

  useEffect(() => {
    setFocused(list[focused] ?? null);
    return () => setFocused(null);
  }, [focused, list, setFocused]);

  const listScrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!split || !selectedId) return;
    const pane = listScrollRef.current;
    const row = pane?.querySelector<HTMLElement>('[aria-current="true"]');
    if (!row) return;
    // Keep DOM focus on the selected row once the user is in the list, so a
    // native Enter/click can't act on a stale, previously clicked row.
    if (pane?.contains(document.activeElement) && document.activeElement !== row) {
      row.focus({ preventScroll: true });
    }
    row.scrollIntoView?.({ block: 'nearest' });
  }, [split, selectedId, selectedIndex]);

  const header = (
    <>
      <div className="flex items-start justify-between gap-3 px-4 pt-5 pb-3 md:px-5 md:pt-4">
        <div>
          <h2 className="text-[22px] font-semibold tracking-tight">{title}</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {description({
              count: list.length,
              loadedCount: list.length,
              hasMore,
              isLoading,
            })}
          </p>
        </div>
        {list.length > 0 && (
          <div className="flex shrink-0 items-center gap-2">
            {action?.({ articles: list })}
            <button
              type="button"
              onClick={() => startListenQueue(list)}
              className="flex min-h-11 shrink-0 items-center gap-1.5 rounded-full border border-border bg-background px-4 text-[13px] font-medium text-foreground hover:bg-muted md:min-h-8 md:px-3 md:text-xs"
            >
              <Headphones className="size-4" aria-hidden="true" />
              Listen
            </button>
          </div>
        )}
      </div>
      {showCategoryFilter && <CategoryFilter />}
      {banner}
    </>
  );

  const content = (
    <>
      {isLoading ? (
        <ArticleListSkeleton />
      ) : isError && list.length === 0 ? (
        <RetryableErrorState
          title="Could not load articles"
          message="The feed request failed. Retry to keep this list distinct from an empty queue."
          onRetry={() => void refetch()}
          isRetrying={isFetching}
        />
      ) : list.length === 0 ? (
        (emptyContent ?? <EmptyState {...empty} />)
      ) : (
        <>
          <SwipeHint
            message={t('articleList.swipeHint')}
            dismissLabel={t('articleList.dismissHint')}
          />
          {list.map((article, index) => (
            <ArticleRow
              key={article.id}
              article={article}
              focused={index === focused}
              showLaterUntil={showLaterUntil}
              to={split ? selectionHref(article.id) : undefined}
              current={split && index === selectedIndex}
            />
          ))}
          {hasMore && (
            <div className="px-4 py-4 md:px-5">
              {isFetchNextPageError ? (
                <div className="mb-2">
                  <InlineError message="Could not load more articles. Try again." />
                </div>
              ) : null}
              <button
                type="button"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => void fetchNextPage()}
                disabled={isFetchingNextPage}
              >
                {isFetchingNextPage ? 'Loading...' : 'Load more'}
              </button>
            </div>
          )}
        </>
      )}
    </>
  );

  if (!split) {
    return (
      <div>
        {header}
        {content}
      </div>
    );
  }

  const prevId = selectedIndex > 0 ? list[selectedIndex - 1].id : null;
  const nextId =
    selectedIndex >= 0 && selectedIndex < list.length - 1 ? list[selectedIndex + 1].id : null;

  return (
    <SplitPaneLayout
      className="flex-1"
      listLabel={title}
      detailLabel={t('articleList.readingPane')}
      listHeader={header}
      list={content}
      listScrollRef={listScrollRef}
      detail={
        selectedId ? (
          <ArticleReader
            variant="pane"
            articleId={selectedId}
            enableShortcuts={false}
            onBack={clearSelection}
            onPrev={() => prevId && select(prevId)}
            onNext={() => nextId && select(nextId)}
            prevId={prevId}
            nextId={nextId}
            onActionComplete={noop}
          />
        ) : (
          <EmptyState
            icon={BookOpen}
            title={t('articleList.selectArticle')}
            subtitle={t('articleList.selectArticleHint')}
            className="h-full"
          />
        )
      }
    />
  );
}

const noop = () => undefined;

export function ArticleListSkeleton() {
  return <ListSkeleton rows={6} />;
}
