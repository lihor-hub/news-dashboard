import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Flame, Loader2 } from 'lucide-react';
import { fetchRecaps } from '../api';
import { NudgeCard } from '../components/FeedNudgeBanner';
import type { WeeklyRecap, WeeklyRecapField } from '../types';

interface PageState {
  recaps: WeeklyRecap[];
  loading: boolean;
  error: string | null;
}

export function WeeklyRecapPage() {
  const [state, setState] = useState<PageState>({ recaps: [], loading: true, error: null });

  useEffect(() => {
    let cancelled = false;
    fetchRecaps()
      .then((recaps) => {
        if (!cancelled) setState({ recaps, loading: false, error: null });
      })
      .catch((err) => {
        if (!cancelled) {
          setState((s) => ({
            ...s,
            loading: false,
            error: err instanceof Error ? err.message : 'Failed to load weekly recaps',
          }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const { recaps, loading, error } = state;
  const [latest, ...history] = recaps;

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center p-8">
        <Loader2 className="text-muted-foreground size-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-5xl space-y-5 p-4 md:p-5">
      <section>
        <h2 className="text-[22px] font-semibold tracking-tight">Weekly Recap</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">A summary of what you read this week</p>
      </section>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {!latest ? (
        <Panel title="This week">
          <EmptyLine />
        </Panel>
      ) : (
        <>
          <section className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <Metric label="Articles read" value={String(latest.data.articles_read)} />
            <Metric label="Minutes read" value={`${latest.data.minutes_read}m`} />
            <Metric label="Streak" value={`${latest.data.current_streak_days}d`} />
            <Metric
              label="Week"
              value={`${formatDate(latest.data.week_start)} – ${formatDate(latest.data.week_end)}`}
            />
          </section>

          {latest.narrative && (
            <Panel title="Your week in review">
              <div className="flex items-start gap-3">
                <div className="flex size-10 shrink-0 items-center justify-center rounded bg-primary/10 text-primary">
                  <Flame className="size-5" />
                </div>
                <div className="space-y-2 text-sm">
                  {latest.narrative
                    .split(/\n\s*\n/)
                    .map((paragraph) => paragraph.trim())
                    .filter(Boolean)
                    .map((paragraph, index) => (
                      <p key={index}>{paragraph}</p>
                    ))}
                </div>
              </div>
            </Panel>
          )}

          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Panel title="Top categories">
              <FieldBars items={latest.data.categories} labelKey="category" />
            </Panel>
            <Panel title="Top sources">
              <FieldBars items={latest.data.sources} labelKey="source" />
            </Panel>
          </section>

          {latest.data.saved && (
            <Panel title="Saved backlog">
              <div className="grid grid-cols-3 gap-3 text-center">
                <SavedStat label="Saved this week" value={latest.data.saved.starred_this_week} />
                <SavedStat label="Read from backlog" value={latest.data.saved.read_from_backlog} />
                <SavedStat label="Backlog" value={latest.data.saved.backlog_total} />
              </div>
            </Panel>
          )}

          {latest.data.dwell && (
            <Panel title="Skim vs deep read">
              <div className="grid grid-cols-3 gap-3 text-center">
                <SavedStat label="Skims" value={latest.data.dwell.skims} />
                <SavedStat label="Deep reads" value={latest.data.dwell.reads} />
                <SavedStat label="Avg. dwell" value={`${latest.data.dwell.average_seconds}s`} />
              </div>
            </Panel>
          )}

          {latest.data.nudges && latest.data.nudges.length > 0 && (
            <Panel title="Suggested changes">
              <div className="-mx-3 space-y-2">
                {latest.data.nudges.map((nudge) => (
                  <NudgeCard key={nudge.id} nudge={nudge} />
                ))}
              </div>
            </Panel>
          )}
        </>
      )}

      {history.length > 0 && (
        <Panel title="Past recaps">
          <ul className="divide-y divide-border">
            {history.map((recap) => (
              <li key={recap.id} className="flex items-center justify-between py-2 text-sm">
                <span className="text-muted-foreground">
                  {formatDate(recap.data.week_start)} – {formatDate(recap.data.week_end)}
                </span>
                <span className="tabular-nums">{recap.data.articles_read} articles</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function SavedStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-md border border-border bg-surface p-3">
      <h3 className="text-sm font-medium">{title}</h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function FieldBars({
  items,
  labelKey,
}: {
  items: WeeklyRecapField[];
  labelKey: 'category' | 'source';
}) {
  if (items.length === 0) return <EmptyLine />;
  const max = Math.max(...items.map((item) => item.count), 1);
  return (
    <div className="space-y-3">
      {items.map((item) => {
        const label = item[labelKey] ?? 'unknown';
        return (
          <div key={label} className="space-y-1">
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="truncate font-medium capitalize">{label}</span>
              <span className="text-muted-foreground tabular-nums">{item.count}</span>
            </div>
            <div className="h-2 overflow-hidden rounded bg-muted">
              <div
                className="h-full bg-chart-1"
                style={{ width: `${(item.count / max) * 100}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function EmptyLine() {
  return (
    <div className="py-8 text-center text-sm text-muted-foreground">
      No recap yet — check back after your first scheduled week.
    </div>
  );
}
