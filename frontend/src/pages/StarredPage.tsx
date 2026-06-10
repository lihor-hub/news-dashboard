import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Star } from 'lucide-react';
import { ArticleRow } from '@/components/article/ArticleRow';
import { EmptyState } from '@/components/EmptyState';
import { CategoryFilter } from '@/components/CategoryFilter';
import { useArticleListNav } from '@/hooks/useArticleListNav';
import { useTriageMutations } from '@/hooks/useTriageMutations';
import { fetchTriageArticles } from '@/api/workflowApi';
import { ARTICLES_KEY } from '@/hooks/useTriageMutations';

export function StarredPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const category = searchParams.get('category') ?? undefined;

  const { data: articles = [], isLoading } = useQuery({
    queryKey: [ARTICLES_KEY, 'starred', category],
    queryFn: () => fetchTriageArticles('starred', category),
  });

  // Sort by starred_at descending
  const list = [...articles].sort(
    (a, b) => +new Date(b.starred_at ?? b.publishedAt) - +new Date(a.starred_at ?? a.publishedAt)
  );

  const mutations = useTriageMutations();
  const { focused } = useArticleListNav(list, (a) => navigate(`/a/${a.id}`), mutations);

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-3">
        <h2 className="text-[22px] font-semibold tracking-tight">Starred</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          {isLoading ? '…' : `${list.length} reference articles`} · always available to Ask AI
        </p>
      </div>
      <CategoryFilter />
      {isLoading ? null : list.length === 0 ? (
        <EmptyState
          icon={Star}
          title="No stars yet"
          subtitle="Star articles you want to keep as reference material."
        />
      ) : (
        list.map((a, i) => <ArticleRow key={a.id} article={a} focused={i === focused} />)
      )}
    </div>
  );
}
