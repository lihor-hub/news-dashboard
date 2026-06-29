import { Clock } from 'lucide-react';
import { ArticleListView } from '@/components/article/ArticleListView';
import { fetchTriageArticles } from '@/api/workflowApi';
import { ARTICLES_KEY } from '@/hooks/useTriageMutations';
import type { WorkflowArticle } from '@/lib/workflowTypes';

function sortByReturnDate(articles: WorkflowArticle[]) {
  return [...articles].sort(
    (a, b) => +new Date(a.later_until ?? 0) - +new Date(b.later_until ?? 0)
  );
}

export function LaterPage() {
  return (
    <ArticleListView
      title="Later"
      description={({ loadedCount, hasMore }) =>
        `${loadedCount}${hasMore ? '+' : ''} snoozed · returns to Today automatically`
      }
      queryKey={[ARTICLES_KEY, 'later']}
      queryFn={(params) => fetchTriageArticles('later', undefined, params)}
      empty={{
        icon: Clock,
        title: 'Nothing snoozed',
        subtitle: 'Articles you send to Later will appear here with their return date.',
      }}
      showLaterUntil
      sortArticles={sortByReturnDate}
    />
  );
}
