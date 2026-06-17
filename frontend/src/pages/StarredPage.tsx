import { Star } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { ArticleListView } from '@/components/article/ArticleListView';
import { fetchTriageArticles } from '@/api/workflowApi';
import { ARTICLES_KEY } from '@/hooks/useTriageMutations';
import type { WorkflowArticle } from '@/lib/workflowTypes';

function sortByStarredDate(articles: WorkflowArticle[]) {
  return [...articles].sort(
    (a, b) => +new Date(b.starred_at ?? b.publishedAt) - +new Date(a.starred_at ?? a.publishedAt)
  );
}

export function StarredPage() {
  const [searchParams] = useSearchParams();
  const category = searchParams.get('category') ?? undefined;

  return (
    <ArticleListView
      title="Starred"
      description={({ count, isLoading }) =>
        `${isLoading ? '…' : `${count} reference articles`} · always available to Ask AI`
      }
      queryKey={[ARTICLES_KEY, 'starred', category]}
      queryFn={() => fetchTriageArticles('starred', category)}
      empty={{
        icon: Star,
        title: 'No stars yet',
        subtitle: 'Star articles you want to keep as reference material.',
      }}
      showCategoryFilter
      sortArticles={sortByStarredDate}
    />
  );
}
