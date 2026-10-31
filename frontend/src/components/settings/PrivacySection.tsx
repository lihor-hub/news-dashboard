import { useEffect, useState } from 'react';
import { Switch } from '@/components/ui/switch';
import { setAnalyticsAllowed, startAnalytics, stopAnalytics } from '@/lib/analytics';
import { fetchAnalyticsSettings, updateAnalyticsSettings } from '@/api';
import { refreshActivityConsent, pauseActivity } from '@/lib/activity';

export function PrivacySection() {
  const [enabled, setEnabled] = useState(true);
  const [globalEnabled, setGlobalEnabled] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const s = await fetchAnalyticsSettings();
        if (!cancelled) {
          setEnabled(s.enabled);
          setGlobalEnabled(s.global_enabled);
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
    const next = !enabled;
    setEnabled(next);
    setSaving(true);
    try {
      if (!next) pauseActivity();
      await updateAnalyticsSettings({ enabled: next });
      refreshActivityConsent();
      setAnalyticsAllowed(next && globalEnabled);
      if (next && globalEnabled) {
        startAnalytics();
      } else {
        stopAnalytics();
      }
    } catch {
      setEnabled(!next);
      refreshActivityConsent();
    } finally {
      setSaving(false);
    }
  };

  if (!loaded) return null;

  return (
    <section>
      <div className="text-xs uppercase tracking-wider text-subtle font-medium mb-2">Privacy</div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <div className="text-xs font-medium text-foreground">Usage analytics</div>
            <p className="text-xs text-muted-foreground">
              Lets Radar track route views, time-on-app, and article dwell time to improve your
              recommendations and reading insights. Also enables approximate connected, visible,
              focused app time and automatic article-reading evidence. Pauses after five minutes
              idle. Opting out preserves earned badges and manual reading progress.
            </p>
          </div>
          <Switch
            checked={enabled && globalEnabled}
            onCheckedChange={() => void toggleEnabled()}
            disabled={saving || !globalEnabled}
            aria-label="Usage analytics"
          />
        </div>
        {!globalEnabled && (
          <p className="text-xs text-muted-foreground">
            Analytics have been disabled instance-wide by the administrator.
          </p>
        )}
      </div>
    </section>
  );
}
