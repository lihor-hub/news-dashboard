import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Inbox } from 'lucide-react';
import { ArticleRow } from '@/components/article/ArticleRow';
import { EmptyState } from '@/components/EmptyState';
import { CategoryFilter } from '@/components/CategoryFilter';
import { useArticleListNav } from '@/hooks/useArticleListNav';
import { useTriageMutations } from '@/hooks/useTriageMutations';
import { fetchTriageArticles } from '@/api/workflowApi';
import { ARTICLES_KEY } from '@/hooks/useTriageMutations';

export function InboxPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const category = searchParams.get('category') ?? undefined;

  const { data: articles = [], isLoading } = useQuery({
    queryKey: [ARTICLES_KEY, 'today', category],
    queryFn: () => fetchTriageArticles('today', category),
  });

  const mutations = useTriageMutations();
  const { focused } = useArticleListNav(articles, (a) => navigate(`/a/${a.id}`), mutations);

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-3 flex items-baseline justify-between">
        <div>
          <h2 className="text-[22px] font-semibold tracking-tight">Today</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {isLoading ? '…' : `${articles.length} unhandled`} · scan, decide, move on
          </p>
        </div>
      </div>
      <CategoryFilter />
      {isLoading ? (
        <ArticleListSkeleton />
      ) : articles.length === 0 ? (
        <EmptyState icon={Inbox} title="Queue clear" subtitle="Nothing left to triage today." />
      ) : (
        <div>
          {articles.map((a, i) => (
            <ArticleRow key={a.id} article={a} focused={i === focused} />
          ))}
        </div>
      )}
    </div>
  );
}

function ArticleListSkeleton() {
  return (
    <div className="divide-y divide-border">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="px-4 py-3 md:px-5 animate-pulse">
          <div className="h-2.5 bg-muted rounded w-32 mb-2" />
          <div className="h-4 bg-muted rounded w-3/4 mb-2" />
          <div className="h-3 bg-muted rounded w-1/2" />
        </div>
      ))}
    </div>
  );
}
