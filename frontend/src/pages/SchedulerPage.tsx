import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  fetchSchedulerStatus,
  fetchLatestJobRuns,
  setSchedulerInterval,
  pauseScheduler,
  resumeScheduler,
  ingestNow,
  type SchedulerStatus,
  type ScheduledJobRun,
} from '../api';
import { relativeCountdown } from '../lib/format';

const JOB_LABELS: Record<string, string> = {
  digest: 'Daily digest',
  recommendations: 'Recommendations',
  analytics_retention: 'Analytics retention',
  per_user_briefings: 'Per-user briefings',
  briefing: 'Global briefing',
};

const INTERVAL_PRESETS = [
  { label: '15m', value: 15 },
  { label: '30m', value: 30 },
  { label: '1h', value: 60 },
  { label: '3h', value: 180 },
  { label: '6h', value: 360 },
];

export function SchedulerPage() {
  const [status, setStatus] = useState<SchedulerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [customMinutes, setCustomMinutes] = useState('');
  const [actionPending, setActionPending] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [countdown, setCountdown] = useState<string>('—');
  const [jobRuns, setJobRuns] = useState<ScheduledJobRun[]>([]);

  async function loadStatus() {
    try {
      const s = await fetchSchedulerStatus();
      setStatus(s);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to load scheduler status');
    } finally {
      setLoading(false);
    }
  }

  async function loadJobRuns() {
    try {
      const runs = await fetchLatestJobRuns();
      setJobRuns(runs);
    } catch {
      // non-critical — silently ignore if not available
    }
  }

  useEffect(() => {
    void loadStatus();
    void loadJobRuns();
  }, []);

  useEffect(() => {
    if (!status) return;
    if (status.interval_ingest_enabled === false) {
      setCountdown('Externally scheduled');
      return;
    }
    if (status.paused) {
      setCountdown('Paused');
      return;
    }
    setCountdown(relativeCountdown(status.next_run_at));
    const timer = setInterval(() => {
      setCountdown(relativeCountdown(status.next_run_at));
    }, 1000);
    return () => clearInterval(timer);
  }, [status]);

  async function handlePreset(minutes: number) {
    if (status?.interval_ingest_enabled === false) return;
    setActionPending(true);
    try {
      const res = await setSchedulerInterval(minutes);
      setStatus((prev) =>
        prev ? { ...prev, interval_minutes: minutes, next_run_at: res.next_run_at } : prev
      );
      toast.success(`Interval set to ${minutes} minutes`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to set interval');
    } finally {
      setActionPending(false);
    }
  }

  async function handleCustomSave() {
    const mins = parseInt(customMinutes, 10);
    if (!mins || mins < 1) {
      toast.error('Enter a valid number of minutes (≥ 1)');
      return;
    }
    await handlePreset(mins);
    setCustomMinutes('');
  }

  async function handleTogglePause() {
    if (!status) return;
    if (status.interval_ingest_enabled === false) return;
    setActionPending(true);
    try {
      if (status.paused) {
        const res = await resumeScheduler();
        setStatus((prev) =>
          prev ? { ...prev, paused: false, next_run_at: res.next_run_at ?? prev.next_run_at } : prev
        );
        toast.success('Scheduler resumed');
      } else {
        await pauseScheduler();
        setStatus((prev) => (prev ? { ...prev, paused: true, next_run_at: null } : prev));
        toast.success('Scheduler paused');
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to toggle pause');
    } finally {
      setActionPending(false);
    }
  }

  async function handleFetchNow() {
    setIngesting(true);
    const id = toast.loading('Running ingest…');
    try {
      const result = await ingestNow();
      if (result.total_errors > 0) {
        const errCount = result.total_errors;
        toast.warning(
          `Done — ${result.inserted} new article${result.inserted !== 1 ? 's' : ''}, ${errCount} source${errCount !== 1 ? 's' : ''} failed. Check Feeds › Runs for details.`,
          { id, duration: 8000 }
        );
      } else {
        toast.success(`Done — ${result.inserted} new article${result.inserted !== 1 ? 's' : ''}`, {
          id,
        });
      }
    } catch {
      toast.error('Ingest failed', { id });
    } finally {
      setIngesting(false);
    }
  }

  if (loading) {
    return (
      <div className="p-4 md:p-5 space-y-4 max-w-2xl">
        <Skeleton className="h-28 w-full rounded-lg" />
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-20 w-full rounded-lg" />
      </div>
    );
  }

  return (
    <div className="p-4 md:p-5 max-w-2xl space-y-4">
      <div className="rounded-lg border border-border p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
          Status
        </h3>
        <div className="flex items-center gap-3 mb-2">
          <Badge
            variant={
              status?.paused || status?.interval_ingest_enabled === false ? 'secondary' : 'default'
            }
          >
            {status?.interval_ingest_enabled === false
              ? 'External schedule'
              : status?.paused
                ? '⏸ Paused'
                : '▶ Running'}
          </Badge>
          <span className="text-sm text-muted-foreground">
            {status?.interval_ingest_enabled === false
              ? 'Interval ingest is managed outside this scheduler'
              : status?.paused
                ? 'No runs scheduled'
                : `Next run in ${countdown}`}
          </span>
        </div>
        <div className="flex gap-2 text-sm mt-2">
          <span className="text-muted-foreground">Interval:</span>
          <span className="font-medium">{status?.interval_minutes ?? '—'} minutes</span>
        </div>
        {status?.interval_ingest_enabled === false && (
          <div className="flex gap-2 text-sm mt-1">
            <span className="text-muted-foreground">Authority:</span>
            <span className="text-muted-foreground">External CronJob</span>
          </div>
        )}
        {status?.interval_ingest_enabled !== false && !status?.paused && status?.next_run_at && (
          <div className="flex gap-2 text-sm mt-1">
            <span className="text-muted-foreground">Next run at:</span>
            <span className="text-muted-foreground">
              {new Date(status.next_run_at).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
          </div>
        )}
      </div>

      <div className="rounded-lg border border-border p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
          Change Interval
        </h3>
        <div className="flex flex-wrap gap-2 mb-3">
          {INTERVAL_PRESETS.map((p) => (
            <Button
              key={p.value}
              size="sm"
              variant={status?.interval_minutes === p.value ? 'default' : 'outline'}
              onClick={() => void handlePreset(p.value)}
              disabled={actionPending || status?.interval_ingest_enabled === false}
            >
              {p.label}
            </Button>
          ))}
        </div>
        <div className="flex gap-2">
          <Input
            type="number"
            min={1}
            placeholder="Custom minutes…"
            value={customMinutes}
            onChange={(e) => setCustomMinutes(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleCustomSave();
            }}
            disabled={actionPending || status?.interval_ingest_enabled === false}
            className="max-w-[180px] h-9"
            aria-label="Custom interval in minutes"
          />
          <Button
            size="sm"
            onClick={() => void handleCustomSave()}
            disabled={actionPending || !customMinutes || status?.interval_ingest_enabled === false}
          >
            Save
          </Button>
        </div>
      </div>

      <div className="rounded-lg border border-border p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
          Controls
        </h3>
        <div className="flex gap-2">
          <Button
            variant={status?.paused ? 'default' : 'secondary'}
            onClick={() => void handleTogglePause()}
            disabled={actionPending || status?.interval_ingest_enabled === false}
          >
            {status?.paused ? '▶ Resume' : '⏸ Pause'}
          </Button>
          <Button
            variant="outline"
            onClick={() => void handleFetchNow()}
            disabled={ingesting || actionPending}
          >
            {ingesting ? '⟳ Fetching…' : '↻ Fetch now'}
          </Button>
        </div>
      </div>

      {jobRuns.length > 0 && (
        <div className="rounded-lg border border-border p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            Last Job Outcomes
          </h3>
          <div className="space-y-2">
            {jobRuns.map((run) => (
              <div key={run.job_name} className="flex items-start gap-3 text-sm">
                <Badge
                  variant={
                    run.status === 'success'
                      ? 'default'
                      : run.status === 'skipped'
                        ? 'secondary'
                        : 'destructive'
                  }
                  className="shrink-0 mt-0.5"
                >
                  {run.status}
                </Badge>
                <div className="min-w-0">
                  <span className="font-medium">{JOB_LABELS[run.job_name] ?? run.job_name}</span>
                  {run.started_at && (
                    <span className="ml-2 text-muted-foreground">
                      {new Date(run.started_at).toLocaleString([], {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  )}
                  {run.duration_ms != null && (
                    <span className="ml-2 text-muted-foreground">{run.duration_ms}ms</span>
                  )}
                  {run.message && (
                    <p className="text-muted-foreground truncate mt-0.5">{run.message}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
