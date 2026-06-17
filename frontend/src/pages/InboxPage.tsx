import { Inbox } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { ArticleListView } from '@/components/article/ArticleListView';
import { fetchTriageArticles } from '@/api/workflowApi';
import { ARTICLES_KEY } from '@/hooks/useTriageMutations';

export function InboxPage() {
  const [searchParams] = useSearchParams();
  const category = searchParams.get('category') ?? undefined;

  return (
    <ArticleListView
      title="Today"
      description={({ count, isLoading }) =>
        `${isLoading ? '…' : `${count} unhandled`} · scan, decide, move on`
      }
      queryKey={[ARTICLES_KEY, 'today', category]}
      queryFn={() => fetchTriageArticles('today', category)}
      empty={{ icon: Inbox, title: 'Queue clear', subtitle: 'Nothing left to triage today.' }}
      showCategoryFilter
    />
  );
}
