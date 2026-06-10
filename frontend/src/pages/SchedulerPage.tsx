import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  fetchSchedulerStatus,
  setSchedulerInterval,
  pauseScheduler,
  resumeScheduler,
  ingestNow,
  type SchedulerStatus,
} from '../api';
import { relativeCountdown } from '../lib/format';

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

  useEffect(() => {
    void loadStatus();
  }, []);

  useEffect(() => {
    if (!status) return;
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
      toast.success(`Done — ${result.inserted} new article${result.inserted !== 1 ? 's' : ''}`, {
        id,
      });
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
          <Badge variant={status?.paused ? 'secondary' : 'default'}>
            {status?.paused ? '⏸ Paused' : '▶ Running'}
          </Badge>
          <span className="text-sm text-muted-foreground">
            {status?.paused ? 'No runs scheduled' : `Next run in ${countdown}`}
          </span>
        </div>
        <div className="flex gap-2 text-sm mt-2">
          <span className="text-muted-foreground">Interval:</span>
          <span className="font-medium">{status?.interval_minutes ?? '—'} minutes</span>
        </div>
        {!status?.paused && status?.next_run_at && (
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
              disabled={actionPending}
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
            disabled={actionPending}
            className="max-w-[180px] h-9"
            aria-label="Custom interval in minutes"
          />
          <Button
            size="sm"
            onClick={() => void handleCustomSave()}
            disabled={actionPending || !customMinutes}
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
            disabled={actionPending}
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
    </div>
  );
}
