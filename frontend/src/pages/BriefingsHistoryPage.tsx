import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Newspaper, AlertCircle, ChevronRight, Check, Copy, RefreshCw, Rss } from 'lucide-react';
import { toast } from 'sonner';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { fetchBriefings, fetchPodcastFeedToken, regeneratePodcastFeedToken } from '@/api';
import { formatDate, formatWindow } from '@/lib/briefingUtils';
import type { Briefing } from '@/types';

// ── Sub-components ────────────────────────────────────────────────────────────

function BriefingRow({ briefing }: { briefing: Briefing }) {
  const isFailed = briefing.status === 'failed';
  return (
    <Link
      to={`/briefs/${briefing.id}`}
      className="flex items-center gap-3 px-4 md:px-5 py-3.5 border-b border-border hover:bg-surface transition-colors group"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          {isFailed ? (
            <span className="flex items-center gap-1 text-[10px] font-medium text-destructive bg-destructive/10 border border-destructive/20 px-1.5 py-0.5 rounded-full">
              <AlertCircle className="size-2.5" />
              Failed
            </span>
          ) : null}
          <span className="text-[11px] text-muted-foreground tabular-nums">
            {formatDate(briefing.created_at)}
          </span>
          {briefing.since_at && briefing.until_at && (
            <span className="text-[11px] text-subtle">
              · {formatWindow(briefing.since_at, briefing.until_at)}
            </span>
          )}
        </div>
        <div className="text-sm font-medium text-foreground leading-snug mt-0.5 group-hover:text-foreground line-clamp-1">
          {isFailed ? (
            <span className="text-muted-foreground italic">Generation failed</span>
          ) : (
            briefing.title || 'Untitled briefing'
          )}
        </div>
        {briefing.summary && !isFailed && (
          <div className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
            {briefing.summary}
          </div>
        )}
        {briefing.error && isFailed && (
          <div className="text-xs text-destructive/70 mt-0.5 font-mono line-clamp-1">
            {briefing.error}
          </div>
        )}
      </div>
      <ChevronRight className="size-4 text-subtle shrink-0 group-hover:text-muted-foreground transition-colors" />
    </Link>
  );
}

function PodcastFeedCard() {
  const queryClient = useQueryClient();
  const [copied, setCopied] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ['briefings', 'podcast-feed-token'],
    queryFn: fetchPodcastFeedToken,
  });

  const regenerate = useMutation({
    mutationFn: regeneratePodcastFeedToken,
    onSuccess: (token) => {
      queryClient.setQueryData(['briefings', 'podcast-feed-token'], token);
      toast('Podcast feed URL regenerated — the old link no longer works');
    },
    onError: () => toast('Failed to regenerate podcast feed URL'),
  });

  const copyUrl = () => {
    if (!data) return;
    void navigator.clipboard.writeText(data.url).then(() => {
      setCopied(true);
      toast('Podcast feed URL copied');
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div className="mx-4 md:mx-5 mb-3 rounded-lg border border-border bg-surface px-4 py-3 flex items-center gap-3">
      <Rss className="size-4 text-accent shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-foreground">Subscribe as a podcast</div>
        <div className="text-xs text-muted-foreground mt-0.5">
          Listen to your daily brief in any podcast app using your personal feed link.
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={copyUrl}
          disabled={isLoading || !data}
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied ? 'Copied' : 'Copy feed URL'}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label="Regenerate podcast feed URL (revokes the old one)"
          onClick={() => regenerate.mutate()}
          disabled={regenerate.isPending}
        >
          <RefreshCw className={`size-3.5 ${regenerate.isPending ? 'animate-spin' : ''}`} />
        </Button>
      </div>
    </div>
  );
}

function HistorySkeleton() {
  return (
    <div className="divide-y divide-border">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="px-4 md:px-5 py-3.5">
          <Skeleton className="h-3 w-32 mb-2" />
          <Skeleton className="h-4 w-3/4 mb-1.5" />
          <Skeleton className="h-3 w-2/3" />
        </div>
      ))}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function BriefingsHistoryPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['briefings', 'list'],
    queryFn: () => fetchBriefings(50, 0),
  });

  const briefings = data?.items ?? [];

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-3">
        <h2 className="text-[22px] font-semibold tracking-tight">Briefing History</h2>
        <p className="text-xs text-muted-foreground mt-0.5">All generated daily briefs</p>
      </div>

      <PodcastFeedCard />

      {isLoading ? (
        <HistorySkeleton />
      ) : briefings.length === 0 ? (
        <div className="flex flex-col items-center justify-center text-center py-20 text-muted-foreground px-4">
          <Newspaper className="size-10 text-subtle mb-3" strokeWidth={1.25} />
          <div className="text-sm font-medium text-foreground">No briefings yet</div>
          <div className="text-xs mt-1 max-w-xs">
            Go to{' '}
            <Link to="/" className="text-accent hover:underline">
              Brief
            </Link>{' '}
            to generate your first daily briefing.
          </div>
        </div>
      ) : (
        <div>
          {briefings.map((b) => (
            <BriefingRow key={b.id} briefing={b} />
          ))}
        </div>
      )}
    </div>
  );
}
