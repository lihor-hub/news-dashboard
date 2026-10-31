import { useQuery } from '@tanstack/react-query';
import { fetchActivity } from '@/api/activity';
import { Button } from './ui/button';

import { activeDuration } from '@/lib/format';

export function ActivityProgress({ accountId }: { accountId: number }) {
  const activity = useQuery({ queryKey: ['activity', accountId], queryFn: fetchActivity });
  if (activity.isPending) return <p>Loading active time…</p>;
  if (activity.isError)
    return (
      <div role="status">
        Active time is unavailable; saved progress has not changed.{' '}
        <Button
          variant="outline"
          className="h-auto min-h-9 max-w-full whitespace-normal"
          onClick={() => void activity.refetch()}
        >
          Retry active time
        </Button>
      </div>
    );
  const value = activity.data;
  if (!value.available) return null;
  return (
    <div className="space-y-1" aria-label="Approximate active time">
      <h3 className="font-medium">Approximate active time</h3>
      <p>
        Measured active time: <strong>{activeDuration(value.total_ms)}</strong>
      </p>
      <p>
        {value.measured_since ? (
          <>
            Measured since{' '}
            <time dateTime={value.measured_since}>
              {new Date(value.measured_since).toLocaleDateString()}
            </time>
            .
          </>
        ) : (
          'No active time measured yet. This is not a complete lifetime zero.'
        )}
      </p>
      {!value.measurement_enabled && (
        <p>
          Measurement is disabled by your usage analytics preference or the administrator. Earned
          badges remain.
        </p>
      )}
      <p>
        {value.next_target_ms
          ? `Next time badge: ${activeDuration(value.next_target_ms)} (${activeDuration(Math.max(0, value.next_target_ms - value.total_ms))} remaining).`
          : 'All time badges earned.'}
      </p>
      <p className="text-sm text-muted-foreground">
        Coverage incomplete ({value.coverage.status}). Connected, visible and focused app use only;
        pauses after five minutes idle. Offline use and background audio do not count. Suspension or
        a failed final send may lose time. App time does not qualify an article read.
      </p>
      {value.coverage.reasons.includes('consent_gap') && (
        <p>Coverage includes a consent gap; reenabling does not restore missed time.</p>
      )}
      {value.coverage.reasons.includes('timezone_change') && (
        <p>Timezone changed; past local-day totals remain frozen.</p>
      )}
    </div>
  );
}
