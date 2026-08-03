import { useEffect } from 'react';
import { isRouteErrorResponse, Link, useRevalidator, useRouteError } from 'react-router';
import { Button } from '@/components/ui/button';
import { reportError } from '@/lib/errorTracking';
import { isChunkLoadError } from '@/lib/chunkError';

// Rendered as a route `errorElement` for errors React Router catches before
// any inner React error boundary (e.g. AppShell's) gets a chance to — most
// notably route matching/loader errors and render errors on routes that
// aren't wrapped by AppShell (login, standalone article view).
export function RouteErrorRecovery() {
  const error = useRouteError();
  const revalidator = useRevalidator();

  useEffect(() => {
    if (!isRouteErrorResponse(error)) {
      reportError(error);
    }
  }, [error]);

  const chunkError = isChunkLoadError(error);
  const notFound = isRouteErrorResponse(error) && error.status === 404;

  const title = notFound
    ? 'Page not found'
    : chunkError
      ? 'A new version is available'
      : 'Something went wrong';
  const message = notFound
    ? "The page you're looking for doesn't exist or has been moved."
    : chunkError
      ? 'This page was updated since it loaded. Reload to get the latest version.'
      : 'An unexpected error occurred while loading this page.';

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-lg font-semibold text-foreground">{title}</h1>
      <p className="max-w-sm text-sm text-muted-foreground">{message}</p>
      <div className="flex items-center gap-3">
        {!notFound && !chunkError && (
          <Button variant="outline" onClick={() => revalidator.revalidate()}>
            Try again
          </Button>
        )}
        <Button variant={notFound ? 'default' : 'outline'} asChild>
          <Link to="/">Go home</Link>
        </Button>
        {chunkError && <Button onClick={() => window.location.reload()}>Reload</Button>}
      </div>
    </div>
  );
}
