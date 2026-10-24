import { Inbox, Star } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router';
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
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const category = searchParams.get('category') ?? undefined;

  return (
    <ArticleListView
      title="Starred"
      description={({ loadedCount, hasMore, isLoading }) =>
        `${isLoading ? '...' : `${loadedCount}${hasMore ? '+' : ''} reference articles`} · always available to Ask AI`
      }
      queryKey={[ARTICLES_KEY, 'starred', category]}
      queryFn={(params) => fetchTriageArticles('starred', category, params)}
      empty={{
        icon: Star,
        title: 'No stars yet',
        subtitle: 'Star articles you want to keep as reference material.',
        actions: [{ label: t('states.actions.today'), to: '/today', icon: Inbox }],
      }}
      showCategoryFilter
      sortArticles={sortByStarredDate}
    />
  );
}
