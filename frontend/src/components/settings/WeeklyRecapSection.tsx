import { useEffect, useState } from 'react';
import { Switch } from '@/components/ui/switch';
import { fetchNotificationSettings, updateNotificationSettings } from '@/api';

const RECAP_DAYS: { value: string; label: string }[] = [
  { value: 'mon', label: 'Monday' },
  { value: 'tue', label: 'Tuesday' },
  { value: 'wed', label: 'Wednesday' },
  { value: 'thu', label: 'Thursday' },
  { value: 'fri', label: 'Friday' },
  { value: 'sat', label: 'Saturday' },
  { value: 'sun', label: 'Sunday' },
];

export function WeeklyRecapSection() {
  const [recapEnabled, setRecapEnabled] = useState(true);
  const [recapDay, setRecapDay] = useState('mon');
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const s = await fetchNotificationSettings();
        if (!cancelled) {
          setRecapEnabled(s.recap_enabled);
          setRecapDay(s.recap_day);
        }
      } catch {
        // keep defaults if settings fail to load
      } finally {
        if (!cancelled) setLoaded(true);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleEnabled = async () => {
    const next = !recapEnabled;
    setRecapEnabled(next);
    setSaving(true);
    try {
      await updateNotificationSettings({ recap_enabled: next });
    } catch {
      setRecapEnabled(!next);
    } finally {
      setSaving(false);
    }
  };

  const handleDayChange = async (day: string) => {
    setRecapDay(day);
    setSaving(true);
    try {
      await updateNotificationSettings({ recap_day: day });
    } catch {
      // non-critical — cadence preference will resync on next load
    } finally {
      setSaving(false);
    }
  };

  if (!loaded) return null;

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        Weekly Recap
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <div className="text-xs font-medium text-foreground">Send weekly recap</div>
            <p className="text-[11px] text-muted-foreground">
              A summary of your reading week, delivered via push.
            </p>
          </div>
          <Switch
            checked={recapEnabled}
            onCheckedChange={() => void toggleEnabled()}
            disabled={saving}
            aria-label="Send weekly recap"
          />
        </div>

        {recapEnabled && (
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground" htmlFor="recap-day">
              Delivery day
            </label>
            <select
              id="recap-day"
              value={recapDay}
              onChange={(e) => void handleDayChange(e.target.value)}
              className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              {RECAP_DAYS.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <p className="text-[11px] text-muted-foreground">
              Delivered at your daily brief time, in your briefing timezone.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
