import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { Send, ExternalLink, Ban } from 'lucide-react';
import { EmptyState } from '@/components/EmptyState';
import { fetchReceivedShares, fetchSentShares, markShareRead, revokeShare } from '@/api';
import { relativeTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { ReceivedShare, SentShare } from '@/types';

const SHARES_KEY = ['shares'];
const SENT_SHARES_KEY = ['shares-sent'];

type Tab = 'received' | 'sent';

function ReceivedTab() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: SHARES_KEY,
    queryFn: fetchReceivedShares,
    staleTime: 15_000,
  });

  const shares: ReceivedShare[] = data?.items ?? [];

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

  if (!isLoading && shares.length === 0) {
    return (
      <EmptyState
        icon={Send}
        title="Nothing shared yet"
        subtitle="When someone sends you an article, it shows up here."
      />
    );
  }

  return (
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
  );
}

function SentTab() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: SENT_SHARES_KEY,
    queryFn: fetchSentShares,
    staleTime: 15_000,
  });

  const shares: SentShare[] = data?.items ?? [];

  const revokeMutation = useMutation({
    mutationFn: (shareId: number) => revokeShare(shareId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SENT_SHARES_KEY });
    },
  });

  if (!isLoading && shares.length === 0) {
    return (
      <EmptyState
        icon={Send}
        title="Nothing sent yet"
        subtitle="Articles you share with other people show up here."
      />
    );
  }

  return (
    <ul className="flex flex-col gap-2">
      {shares.map((s) => {
        const revoked = Boolean(s.revoked_at);
        return (
          <li
            key={s.id}
            className={cn('rounded-lg border border-border p-3', revoked && 'opacity-60')}
          >
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>
                To <span className="font-medium text-foreground">{s.to_username}</span>
              </span>
              <span>· {relativeTime(s.created_at)}</span>
              {revoked ? (
                <span className="rounded-full bg-surface-2 px-1.5 py-0.5 text-[10px] font-medium uppercase text-muted-foreground">
                  Revoked
                </span>
              ) : s.read_at ? (
                <span className="text-[10px] uppercase text-muted-foreground">Read</span>
              ) : (
                <span className="text-[10px] uppercase text-muted-foreground">Unread</span>
              )}
            </div>

            <div className="mt-1 block font-medium text-foreground">{s.article_title}</div>
            <div className="mt-0.5 text-xs text-muted-foreground">{s.article_source_name}</div>

            {s.note ? (
              <div className="mt-2 rounded-md bg-surface-2 px-2.5 py-1.5 text-sm text-foreground">
                "{s.note}"
              </div>
            ) : null}

            <div className="mt-2 flex items-center gap-3 text-xs">
              <a
                href={s.article_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
              >
                Original <ExternalLink className="size-3" />
              </a>
              {!revoked ? (
                <button
                  type="button"
                  onClick={() => revokeMutation.mutate(s.id)}
                  disabled={revokeMutation.isPending}
                  className="inline-flex items-center gap-1 text-destructive hover:underline disabled:opacity-50"
                >
                  <Ban className="size-3" />
                  Revoke
                </button>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function SharedPage() {
  const [tab, setTab] = useState<Tab>('received');

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <div className="mb-4">
        <h1 className="text-lg font-semibold text-foreground">Shared</h1>
        <p className="text-sm text-muted-foreground">Articles you've sent and received</p>
      </div>

      <div className="mb-4 flex items-center gap-1 border-b border-border text-sm">
        <button
          type="button"
          onClick={() => setTab('received')}
          className={cn(
            'px-3 py-2 font-medium transition-colors',
            tab === 'received'
              ? 'border-b-2 border-accent-foreground text-foreground'
              : 'text-muted-foreground hover:text-foreground'
          )}
        >
          Received
        </button>
        <button
          type="button"
          onClick={() => setTab('sent')}
          className={cn(
            'px-3 py-2 font-medium transition-colors',
            tab === 'sent'
              ? 'border-b-2 border-accent-foreground text-foreground'
              : 'text-muted-foreground hover:text-foreground'
          )}
        >
          Sent
        </button>
      </div>

      {tab === 'received' ? <ReceivedTab /> : <SentTab />}
    </div>
  );
}
