import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2, TriangleAlert } from 'lucide-react';
import { saveSharedUrl } from '@/api';

function extractSharedUrl(params: URLSearchParams): string {
  const directUrl = params.get('url')?.trim();
  if (directUrl) return directUrl;
  const text = params.get('text') ?? '';
  return /https?:\/\/\S+/.exec(text)?.[0] ?? '';
}

export function ShareTargetPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const sharedUrl = useMemo(() => extractSharedUrl(params), [params]);

  useEffect(() => {
    if (!sharedUrl) {
      setError('No link was shared.');
      return;
    }
    let cancelled = false;
    saveSharedUrl({
      url: sharedUrl,
      title: params.get('title'),
      text: params.get('text'),
    })
      .then((article) => {
        if (!cancelled) void navigate(`/a/${article.id}`, { replace: true });
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not save link.');
      });
    return () => {
      cancelled = true;
    };
  }, [navigate, params, sharedUrl]);

  if (error) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center px-4">
        <div className="max-w-sm text-center">
          <TriangleAlert className="mx-auto mb-3 size-8 text-destructive" />
          <h1 className="text-lg font-semibold text-foreground">Could not save link</h1>
          <p className="mt-2 text-sm text-muted-foreground">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[60vh] items-center justify-center gap-2 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" />
      Saving link...
    </div>
  );
}
