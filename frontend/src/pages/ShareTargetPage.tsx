import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Bookmark, Loader2, Newspaper, TriangleAlert } from 'lucide-react';
import { saveSharedUrl } from '@/api';
import { addReadingListItem } from '@/api/readingListApi';
import { Button } from '@/components/ui/button';

function extractSharedUrl(params: URLSearchParams): string {
  const directUrl = params.get('url')?.trim();
  if (directUrl) return directUrl;
  const text = params.get('text') ?? '';
  return /https?:\/\/\S+/.exec(text)?.[0] ?? '';
}

type PendingAction = 'article' | 'reading-list' | null;

export function ShareTargetPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [pending, setPending] = useState<PendingAction>(null);
  const [error, setError] = useState<string | null>(null);
  const sharedUrl = useMemo(() => extractSharedUrl(params), [params]);
  const title = params.get('title');
  const text = params.get('text');

  async function handleSaveAsArticle() {
    setPending('article');
    setError(null);
    try {
      const article = await saveSharedUrl({ url: sharedUrl, title, text });
      void navigate(`/a/${article.id}`, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save link.');
      setPending(null);
    }
  }

  async function handleSaveToReadingList() {
    setPending('reading-list');
    setError(null);
    try {
      await addReadingListItem(sharedUrl);
      void navigate('/reading-list', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save link.');
      setPending(null);
    }
  }

  if (!sharedUrl) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center px-4">
        <div className="max-w-sm text-center">
          <TriangleAlert className="mx-auto mb-3 size-8 text-destructive" />
          <h1 className="text-lg font-semibold text-foreground">Could not save link</h1>
          <p className="mt-2 text-sm text-muted-foreground">No link was shared.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4">
      <div className="w-full max-w-sm text-center">
        <h1 className="text-lg font-semibold text-foreground">Save shared link</h1>
        <p className="mt-2 truncate text-sm text-muted-foreground">{title ?? sharedUrl}</p>
        {error ? <p className="mt-2 text-sm text-destructive">{error}</p> : null}
        <div className="mt-6 flex flex-col gap-2">
          <Button
            type="button"
            onClick={() => void handleSaveAsArticle()}
            disabled={pending !== null}
          >
            {pending === 'article' ? <Loader2 className="animate-spin" /> : <Newspaper />}
            Save as article
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => void handleSaveToReadingList()}
            disabled={pending !== null}
          >
            {pending === 'reading-list' ? <Loader2 className="animate-spin" /> : <Bookmark />}
            Save to reading list
          </Button>
        </div>
      </div>
    </div>
  );
}
