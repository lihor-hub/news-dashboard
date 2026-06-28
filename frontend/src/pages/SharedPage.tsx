import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Send, ExternalLink } from 'lucide-react';
import { EmptyState } from '@/components/EmptyState';
import { fetchReceivedShares, markShareRead } from '@/api';
import { relativeTime } from '@/lib/format';
import { cn } from '@/lib/utils';

const SHARES_KEY = ['shares'];

export function SharedPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: SHARES_KEY,
    queryFn: fetchReceivedShares,
    staleTime: 15_000,
  });

  const shares = data?.items ?? [];

  // Opening the page clears the unread badge: mark every unread share as read
  // once, then refresh the badge query other surfaces rely on.
  useEffect(() => {
    const unread = shares.filter((s) => !s.read_at);
    if (unread.length === 0) return;
    let cancelled = false;
    void Promise.all(unread.map((s) => markShareRead(s.id))).then(() => {
      if (cancelled) return;
      void queryClient.invalidateQueries({ queryKey: ['shares-unread'] });
    });
    return () => {
      cancelled = true;
    };
    // Run when the set of unread ids changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shares.map((s) => (s.read_at ? '' : s.id)).join(',')]);

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <div className="mb-4">
        <h1 className="text-lg font-semibold text-foreground">Shared with me</h1>
        <p className="text-sm text-muted-foreground">
          {isLoading ? '…' : `${shares.length} article${shares.length === 1 ? '' : 's'}`} sent to
          you by other people
        </p>
      </div>

      {!isLoading && shares.length === 0 ? (
        <EmptyState
          icon={Send}
          title="Nothing shared yet"
          subtitle="When someone sends you an article, it shows up here."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {shares.map((s) => (
            <li
              key={s.id}
              className={cn('rounded-lg border border-border p-3', !s.read_at && 'bg-surface')}
            >
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                {!s.read_at && (
                  <span className="size-2 shrink-0 rounded-full bg-signal-high" aria-hidden />
                )}
                <span className="font-medium text-foreground">{s.from_username}</span>
                <span>shared · {relativeTime(s.created_at)}</span>
              </div>

              <Link
                to={`/shared/${s.id}`}
                className="mt-1 block font-medium text-foreground hover:underline"
              >
                {s.article_title}
              </Link>
              <div className="mt-0.5 text-xs text-muted-foreground">{s.article_source_name}</div>

              {s.note ? (
                <div className="mt-2 rounded-md bg-surface-2 px-2.5 py-1.5 text-sm text-foreground">
                  "{s.note}"
                </div>
              ) : null}

              <div className="mt-2 flex items-center gap-3 text-xs">
                <Link to={`/shared/${s.id}`} className="text-accent-foreground hover:underline">
                  View
                </Link>
                <a
                  href={s.article_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
                >
                  Original <ExternalLink className="size-3" />
                </a>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
