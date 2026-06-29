import { Archive as ArchiveIcon } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { ArticleListView } from '@/components/article/ArticleListView';
import { fetchTriageArticles } from '@/api/workflowApi';
import { ARTICLES_KEY } from '@/hooks/useTriageMutations';
import type { WorkflowArticle } from '@/lib/workflowTypes';

function sortByArchivedDate(articles: WorkflowArticle[]) {
  return [...articles].sort(
    (a, b) => +new Date(b.archived_at ?? 0) - +new Date(a.archived_at ?? 0)
  );
}

export function ArchivePage() {
  const [searchParams] = useSearchParams();
  const category = searchParams.get('category') ?? undefined;

  return (
    <ArticleListView
      title="Archive"
      description={({ loadedCount, hasMore }) =>
        `${loadedCount}${hasMore ? '+' : ''} archived · still searchable`
      }
      queryKey={[ARTICLES_KEY, 'archived', category]}
      queryFn={(params) => fetchTriageArticles('archived', category, params)}
      empty={{ icon: ArchiveIcon, title: 'Archive empty' }}
      showCategoryFilter
      sortArticles={sortByArchivedDate}
    />
  );
}
