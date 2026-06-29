import { Inbox } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { ArticleListView } from '@/components/article/ArticleListView';
import { FeedNudgeBanner } from '@/components/FeedNudgeBanner';
import { fetchTriageArticles } from '@/api/workflowApi';
import { ARTICLES_KEY } from '@/hooks/useTriageMutations';

export function InboxPage() {
  const [searchParams] = useSearchParams();
  const category = searchParams.get('category') ?? undefined;

  return (
    <ArticleListView
      title="Today"
      description={({ loadedCount, hasMore, isLoading }) =>
        `${isLoading ? '...' : `${loadedCount}${hasMore ? '+' : ''} unhandled`} · scan, decide, move on`
      }
      queryKey={[ARTICLES_KEY, 'today', category]}
      queryFn={(params) => fetchTriageArticles('today', category, params)}
      empty={{ icon: Inbox, title: 'Queue clear', subtitle: 'Nothing left to triage today.' }}
      showCategoryFilter
      banner={<FeedNudgeBanner />}
    />
  );
}
