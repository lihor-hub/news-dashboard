import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import { saveSharedUrl } from '@/api';
import { extractSharedUrl } from '@/lib/shareTarget';

export function ShareTargetPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const sharedUrl = extractSharedUrl(searchParams.get('url'), searchParams.get('text'));
    if (!sharedUrl) {
      setError('No link was found in the shared content.');
      return;
    }

    const title = searchParams.get('title') ?? undefined;
    saveSharedUrl(sharedUrl, title)
      .then((article) => {
        toast('Saved to Later');
        void navigate(`/a/${article.id}`, { replace: true });
      })
      .catch(() => {
        setError('Could not save this link. Please try again.');
      });
  }, [searchParams, navigate]);

  if (error) {
    return (
      <div className="mx-auto flex min-h-[50vh] max-w-md flex-col items-center justify-center gap-3 text-center">
        <AlertTriangle className="size-8 text-muted-foreground" />
        <h1 className="text-lg font-semibold text-foreground">Couldn't save link</h1>
        <p className="text-sm text-muted-foreground">{error}</p>
        <button
          type="button"
          onClick={() => void navigate('/')}
          className="mt-2 inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          Go home
        </button>
      </div>
    );
  }

  return (
    <div className="flex min-h-[50vh] flex-1 items-center justify-center p-8">
      <div className="flex flex-col items-center gap-3">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">Saving shared link…</p>
      </div>
    </div>
  );
}
