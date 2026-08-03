import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { ExternalLink, Trash2, WifiOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { listOfflineArticles, removeOfflineArticle, type OfflineArticle } from '@/lib/offline';

function formatSavedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Saved offline';
  return `Saved ${date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`;
}

export function OfflineSavedPage() {
  const [articles, setArticles] = useState<OfflineArticle[]>(() => listOfflineArticles());
  const hasArticles = articles.length > 0;

  const savedCount = useMemo(
    () => `${articles.length} ${articles.length === 1 ? 'article' : 'articles'}`,
    [articles.length]
  );

  async function removeArticle(articleId: string) {
    await removeOfflineArticle(articleId);
    setArticles(listOfflineArticles());
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-foreground">Offline Saved</h2>
          <p className="text-sm text-muted-foreground">{savedCount}</p>
        </div>
      </div>

      {!hasArticles ? (
        <div className="flex min-h-[240px] flex-col items-center justify-center rounded-lg border border-dashed border-border px-6 text-center">
          <WifiOff className="mb-3 size-7 text-muted-foreground" />
          <h3 className="text-sm font-medium text-foreground">No offline articles</h3>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">
            Saved article bodies will appear here and remain available without a network.
          </p>
        </div>
      ) : (
        <div className="divide-y divide-border rounded-lg border border-border bg-surface">
          {articles.map((article) => (
            <article key={article.id} className="flex gap-3 p-4">
              <div className="min-w-0 flex-1">
                <Link
                  to={`/a/${article.id}`}
                  className="line-clamp-2 text-sm font-medium text-foreground hover:underline"
                >
                  {article.title}
                </Link>
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                  <span>{article.source}</span>
                  <span>{formatSavedAt(article.savedAt)}</span>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button variant="ghost" size="icon" asChild aria-label="Open original">
                  <a href={article.url} target="_blank" rel="noreferrer">
                    <ExternalLink className="size-4" />
                  </a>
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove ${article.title}`}
                  onClick={() => void removeArticle(article.id)}
                >
                  <Trash2 className="size-4" />
                </Button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
