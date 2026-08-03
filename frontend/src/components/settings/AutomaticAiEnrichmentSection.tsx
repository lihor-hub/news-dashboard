import { useEffect, useState } from 'react';
import {
  fetchAutomaticAiEnrichmentSettings,
  updateAutomaticAiEnrichmentSettings,
} from '@/api/settings';
import { Switch } from '@/components/ui/switch';

export function AutomaticAiEnrichmentSection() {
  const [settings, setSettings] = useState<{
    enabled: boolean;
    available: boolean;
    limit: number;
  }>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void fetchAutomaticAiEnrichmentSettings()
      .then((value) => {
        if (!cancelled) setSettings(value);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (!settings) return null;
  const toggle = async () => {
    const previous = settings;
    const enabled = !previous.enabled;
    setSettings({ ...previous, enabled });
    setSaving(true);
    setError(false);
    try {
      setSettings(await updateAutomaticAiEnrichmentSettings({ enabled }));
    } catch {
      setSettings(previous);
      setError(true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">AI</div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-2">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-xs font-medium">Automatic AI article enrichment</div>
            <p className="text-[11px] text-muted-foreground">
              Uses the configured AI model after ingestion for up to {settings.limit} newly ingested
              articles per run. Existing takeaways and perspectives are reused.
            </p>
          </div>
          <Switch
            checked={settings.enabled}
            onCheckedChange={() => void toggle()}
            disabled={
              saving || (!settings.enabled && (!settings.available || settings.limit === 0))
            }
            aria-label="Automatic AI article enrichment"
          />
        </div>
        {!settings.available && (
          <p className="text-[11px] text-muted-foreground">AI credentials are not configured.</p>
        )}
        {settings.limit === 0 && (
          <p className="text-[11px] text-muted-foreground">Background generation is disabled.</p>
        )}
        {error && <p className="text-[11px] text-destructive">Could not save this preference.</p>}
      </div>
    </section>
  );
}
