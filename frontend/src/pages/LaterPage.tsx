import { useState } from 'react';
import { Clock, Download } from 'lucide-react';
import { ArticleListView } from '@/components/article/ArticleListView';
import { fetchTriageArticles } from '@/api/workflowApi';
import { ARTICLES_KEY } from '@/hooks/useTriageMutations';
import type { WorkflowArticle } from '@/lib/workflowTypes';
import { cacheArticleBodies, isOfflineCacheSupported } from '@/lib/offline';

function sortByReturnDate(articles: WorkflowArticle[]) {
  return [...articles].sort(
    (a, b) => +new Date(a.later_until ?? 0) - +new Date(b.later_until ?? 0)
  );
}

export function LaterPage() {
  const [saving, setSaving] = useState(false);
  const [savedCount, setSavedCount] = useState<number | null>(null);

  async function saveArticlesOffline(articles: WorkflowArticle[]): Promise<void> {
    setSaving(true);
    setSavedCount(await cacheArticleBodies(articles.map((article) => article.id)));
    setSaving(false);
  }

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
      action={({ articles }) =>
        isOfflineCacheSupported() && articles.length > 0 ? (
          <button
            type="button"
            onClick={() => void saveArticlesOffline(articles)}
            disabled={saving}
            className="flex shrink-0 items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Download className="size-3.5" />
            {saving ? 'Saving...' : savedCount == null ? 'Save offline' : `${savedCount} saved`}
          </button>
        ) : null
      }
    />
  );
}
