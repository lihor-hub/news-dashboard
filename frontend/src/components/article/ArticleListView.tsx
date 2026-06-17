import { useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, type QueryKey } from '@tanstack/react-query';
import type { LucideIcon } from 'lucide-react';
import { ArticleRow } from '@/components/article/ArticleRow';
import { CategoryFilter } from '@/components/CategoryFilter';
import { EmptyState } from '@/components/EmptyState';
import { useFocusedArticle } from '@/contexts/focusedArticle';
import { useArticleListNav } from '@/hooks/useArticleListNav';
import { useTriageMutations } from '@/hooks/useTriageMutations';
import { setReaderList } from '@/lib/readerList';
import type { WorkflowArticle } from '@/lib/workflowTypes';

interface ArticleListViewProps {
  title: string;
  description: (state: { count: number; isLoading: boolean }) => React.ReactNode;
  queryKey: QueryKey;
  queryFn: () => Promise<WorkflowArticle[]>;
  empty: {
    icon: LucideIcon;
    title: string;
    subtitle?: string;
  };
  showCategoryFilter?: boolean;
  showLaterUntil?: boolean;
  sortArticles?: (articles: WorkflowArticle[]) => WorkflowArticle[];
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
}: ArticleListViewProps) {
  const navigate = useNavigate();
  const { data: articles = [], isLoading } = useQuery({
    queryKey,
    queryFn,
  });

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
          {description({ count: list.length, isLoading })}
        </p>
      </div>
      {showCategoryFilter && <CategoryFilter />}
      {isLoading ? (
        <ArticleListSkeleton />
      ) : list.length === 0 ? (
        <EmptyState icon={empty.icon} title={empty.title} subtitle={empty.subtitle} />
      ) : (
        list.map((article, index) => (
          <ArticleRow
            key={article.id}
            article={article}
            focused={index === focused}
            showLaterUntil={showLaterUntil}
          />
        ))
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
