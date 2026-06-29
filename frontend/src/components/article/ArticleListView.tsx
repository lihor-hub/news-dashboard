import { useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useInfiniteQuery, type QueryKey } from '@tanstack/react-query';
import type { LucideIcon } from 'lucide-react';
import { ArticleRow } from '@/components/article/ArticleRow';
import { CategoryFilter } from '@/components/CategoryFilter';
import { EmptyState } from '@/components/EmptyState';
import { useFocusedArticle } from '@/contexts/focusedArticle';
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
  }) => React.ReactNode;
  queryKey: QueryKey;
  queryFn: (params: { limit: number; offset: number }) => Promise<TriageArticlePage>;
  empty: {
    icon: LucideIcon;
    title: string;
    subtitle?: string;
  };
  showCategoryFilter?: boolean;
  showLaterUntil?: boolean;
  sortArticles?: (articles: WorkflowArticle[]) => WorkflowArticle[];
  banner?: React.ReactNode;
}

export function ArticleListView({
  title,
  description,
  queryKey,
  queryFn,
  empty,
  showCategoryFilter,
  showLaterUntil,
  sortArticles,
  banner,
}: ArticleListViewProps) {
  const navigate = useNavigate();
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } = useInfiniteQuery({
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

  const mutations = useTriageMutations();
  const { focused } = useArticleListNav(list, (article) => navigate(`/a/${article.id}`), mutations);
  const { set: setFocused } = useFocusedArticle();

  useEffect(() => {
    setFocused(list[focused] ?? null);
    return () => setFocused(null);
  }, [focused, list, setFocused]);

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-3">
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
      {showCategoryFilter && <CategoryFilter />}
      {banner}
      {isLoading ? (
        <ArticleListSkeleton />
      ) : list.length === 0 ? (
        <EmptyState icon={empty.icon} title={empty.title} subtitle={empty.subtitle} />
      ) : (
        <>
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
  return (
    <div className="divide-y divide-border">
      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="px-4 py-3 md:px-5 animate-pulse">
          <div className="h-2.5 bg-muted rounded w-32 mb-2" />
          <div className="h-4 bg-muted rounded w-3/4 mb-2" />
          <div className="h-3 bg-muted rounded w-1/2" />
        </div>
      ))}
    </div>
  );
}
