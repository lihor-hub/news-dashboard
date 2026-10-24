import { useEffect, useMemo } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { useInfiniteQuery, type QueryKey } from '@tanstack/react-query';
import { Headphones } from 'lucide-react';
import { ArticleRow } from '@/components/article/ArticleRow';
import { SwipeHint } from '@/components/article/SwipeableRow';
import { CategoryFilter } from '@/components/CategoryFilter';
import { EmptyState, type EmptyStateProps } from '@/components/EmptyState';
import { InlineError, ListSkeleton, RetryableErrorState } from '@/components/PageState';
import { useFocusedArticle } from '@/contexts/focusedArticle';
import { useListenQueue } from '@/contexts/listenQueue';
import { useArticleListNav } from '@/hooks/useArticleListNav';
import { useTriageMutations } from '@/hooks/useTriageMutations';
import { setReaderList } from '@/lib/readerList';
import type { WorkflowArticle } from '@/lib/workflowTypes';
import type { TriageArticlePage } from '@/api/workflowApi';

const ARTICLE_PAGE_SIZE = 100;

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
}: ArticleListViewProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
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
  const { focused } = useArticleListNav(
    list,
    (article) => void navigate(`/a/${article.id}`),
    mutations
  );
  const { set: setFocused } = useFocusedArticle();

  useEffect(() => {
    setFocused(list[focused] ?? null);
    return () => setFocused(null);
  }, [focused, list, setFocused]);

  return (
    <div>
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
    </div>
  );
}

export function ArticleListSkeleton() {
  return <ListSkeleton rows={6} />;
}
