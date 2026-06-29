import { useEffect, useState } from 'react';
import {
  Sun,
  Moon,
  Monitor,
  RefreshCw,
  Download,
  RotateCcw,
  ExternalLink,
  Sparkles,
  Bell,
  BellOff,
} from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useTheme } from '@/hooks/useTheme';
import { cn } from '@/lib/utils';
import type { Theme } from '@/lib/theme';
import { useUpdateCheck } from '@/hooks/useUpdateCheck';
import {
  downloadUserExport,
  fetchNotificationSettings,
  recalculateMyRecommendations,
  subscribePush,
  unsubscribePush,
  updateNotificationSettings,
} from '@/api';
import { ARTICLES_KEY } from '@/hooks/useTriageMutations';

const THEME_OPTS: { v: Theme; label: string; Icon: React.ComponentType<{ className?: string }> }[] =
  [
    { v: 'light', label: 'Light', Icon: Sun },
    { v: 'dark', label: 'Dark', Icon: Moon },
    { v: 'system', label: 'System', Icon: Monitor },
  ];

function UpdatesSection() {
  const {
    platform,
    info,
    loading,
    error,
    check,
    electronStage,
    downloadPercent,
    electronLatestVersion,
    checkElectron,
    downloadElectronUpdate,
    installElectronUpdate,
  } = useUpdateCheck();

  // On Electron: wire IPC and kick off the auto-updater check immediately.
  useEffect(() => {
    if (platform === 'electron') {
      checkElectron();
      return () => window.electronAPI?.removeUpdateListeners();
    }
  }, [platform, checkElectron]);

  const sectionLabel = (
    <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">Updates</div>
  );

  // ── Electron ──────────────────────────────────────────────────────────────
  if (platform === 'electron') {
    const appVersion = window.electronAPI?.appVersion ?? '…';

    return (
      <section>
        {sectionLabel}
        <div className="rounded-lg border border-border bg-card p-4 space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Current version</span>
            <span className="tabular-nums font-mono text-xs">{appVersion}</span>
          </div>

          {electronStage === 'idle' && (
            <p className="text-xs text-muted-foreground">Checking for updates…</p>
          )}

          {electronStage === 'checking' && (
            <p className="text-xs text-muted-foreground flex items-center gap-1.5">
              <RefreshCw className="size-3 animate-spin" />
              Checking for updates…
            </p>
          )}

          {electronStage === 'up-to-date' && (
            <p className="text-xs text-green-600 dark:text-green-400">
              You're on the latest version.
            </p>
          )}

          {electronStage === 'available' && (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">
                Version <span className="font-mono">{electronLatestVersion}</span> is available.
              </p>
              <button
                onClick={downloadElectronUpdate}
                className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                <Download className="size-3" />
                Download update
              </button>
            </div>
          )}

          {electronStage === 'downloading' && (
            <div className="space-y-1.5">
              <p className="text-xs text-muted-foreground">Downloading… {downloadPercent}%</p>
              <div className="h-1.5 rounded-full bg-surface-2 overflow-hidden">
                <div
                  className="h-full bg-primary transition-all duration-300"
                  style={{ width: `${downloadPercent}%` }}
                />
              </div>
            </div>
          )}

          {electronStage === 'ready' && (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">Update downloaded. Restart to apply.</p>
              <button
                onClick={installElectronUpdate}
                className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                <RotateCcw className="size-3" />
                Restart and install
              </button>
            </div>
          )}

          {electronStage === 'error' && (
            <div className="space-y-2">
              <p className="text-xs text-destructive">{error ?? 'Update check failed.'}</p>
              <button
                onClick={checkElectron}
                className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                Try again
              </button>
            </div>
          )}
        </div>
      </section>
    );
  }

  // ── Android TWA ───────────────────────────────────────────────────────────
  if (platform === 'twa') {
    return (
      <section>
        {sectionLabel}
        <div className="rounded-lg border border-border bg-card p-4 space-y-3">
          {info && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">App version</span>
              <span className="tabular-nums font-mono text-xs">
                {info.installedVersionKnown ? info.currentVersion : 'Unknown'}
              </span>
            </div>
          )}

          {!info && !loading && (
            <button
              onClick={() => void check()}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
            >
              <RefreshCw className="size-3" />
              Check for updates
            </button>
          )}

          {loading && (
            <p className="text-xs text-muted-foreground flex items-center gap-1.5">
              <RefreshCw className="size-3 animate-spin" />
              Checking…
            </p>
          )}

          {error && <p className="text-xs text-destructive">{error}</p>}

          {info && !loading && (
            <div className="space-y-2">
              {info.apkUrl ? (
                <>
                  <p className="text-xs text-muted-foreground">
                    Version <span className="font-mono">{info.latestVersion}</span> is available for
                    download.
                  </p>
                  <div className="space-y-1.5">
                    <a
                      href={info.apkUrl}
                      className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors w-fit"
                    >
                      <Download className="size-3" />
                      Download APK
                    </a>
                    <p className="text-[11px] text-subtle">
                      Android will prompt you to confirm the install — tap Install when it appears.
                    </p>
                  </div>
                </>
              ) : (
                <a
                  href={info.releaseUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs text-primary hover:underline"
                >
                  <ExternalLink className="size-3" />
                  View Android releases
                </a>
              )}
            </div>
          )}

          {info && (
            <button
              onClick={() => void check()}
              className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              Check again
            </button>
          )}
        </div>
      </section>
    );
  }

  // ── Web / PWA ─────────────────────────────────────────────────────────────
  return (
    <section>
      {sectionLabel}
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        {info && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Version</span>
            <span className="tabular-nums font-mono text-xs">{info.currentVersion}</span>
          </div>
        )}

        {!info && !loading && (
          <button
            onClick={() => void check()}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
          >
            <RefreshCw className="size-3" />
            Check version
          </button>
        )}

        {loading && (
          <p className="text-xs text-muted-foreground flex items-center gap-1.5">
            <RefreshCw className="size-3 animate-spin" />
            Loading…
          </p>
        )}

        {error && <p className="text-xs text-destructive">{error}</p>}

        {info && (
          <>
            <p className="text-xs text-muted-foreground">
              The web app is always current — the live site updates automatically on each release.
            </p>
            <a
              href={`https://github.com/${info.releaseUrl.split('github.com/')[1]?.split('/releases')[0] ?? 'ioachim-hub/news-dashboard'}/releases`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-primary hover:underline w-fit"
            >
              <ExternalLink className="size-3" />
              Release history
            </a>
          </>
        )}
      </div>
    </section>
  );
}

type RecalcState =
  | { status: 'idle' }
  | { status: 'running' }
  | { status: 'done'; scored: number }
  | { status: 'error' };

function PersonalizationSection() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<RecalcState>({ status: 'idle' });

  const recalculate = async () => {
    setState({ status: 'running' });
    try {
      const { scored } = await recalculateMyRecommendations();
      setState({ status: 'done', scored });
      // Invalidate cached article data so recommendation scores refresh on next render.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: [ARTICLES_KEY] }),
        queryClient.invalidateQueries({ queryKey: ['article'] }),
      ]);
    } catch {
      setState({ status: 'error' });
    }
  };

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        Personalization
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <p className="text-xs text-muted-foreground">
          Recommendations are learned from articles you star, read, or skip. Refresh to recompute
          your personalized scores now.
        </p>
        <button
          onClick={() => void recalculate()}
          disabled={state.status === 'running'}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
        >
          {state.status === 'running' ? (
            <RefreshCw className="size-3 animate-spin" />
          ) : (
            <Sparkles className="size-3" />
          )}
          {state.status === 'running' ? 'Refreshing…' : 'Refresh recommendations'}
        </button>

        {state.status === 'done' && state.scored > 0 && (
          <p className="text-xs text-green-600 dark:text-green-400">
            Personalized {state.scored} {state.scored === 1 ? 'article' : 'articles'}. Your feed is
            up to date.
          </p>
        )}
        {state.status === 'done' && state.scored === 0 && (
          <p className="text-xs text-muted-foreground">
            Nothing to personalize yet — star, read, or skip a few articles first, then refresh.
          </p>
        )}
        {state.status === 'error' && (
          <p className="text-xs text-destructive">Couldn't refresh recommendations. Try again.</p>
        )}
      </div>
    </section>
  );
}

function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  return new Uint8Array([...raw].map((c) => c.charCodeAt(0)));
}

type PushState = 'idle' | 'requesting' | 'subscribed' | 'denied' | 'unavailable' | 'error';

function DailyBriefSection() {
  const [briefingTime, setBriefingTime] = useState('09:00');
  const [briefingTimezone, setBriefingTimezone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone
  );
  const [pushEnabled, setPushEnabled] = useState(false);
  const [vapidKey, setVapidKey] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [timeSaving, setTimeSaving] = useState(false);
  const [pushState, setPushState] = useState<PushState>('idle');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const s = await fetchNotificationSettings();
        if (!cancelled) {
          setBriefingTime(s.briefing_time);
          setBriefingTimezone(
            s.briefing_timezone || Intl.DateTimeFormat().resolvedOptions().timeZone
          );
          setPushEnabled(s.push_enabled);
          setVapidKey(s.vapid_public_key);
          if (s.push_enabled) setPushState('subscribed');
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

  const handleTimeBlur = async (t: string) => {
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(t)) return;
    setTimeSaving(true);
    try {
      await updateNotificationSettings({ briefing_time: t });
    } catch {
      // non-critical — time preference will resync on next load
    } finally {
      setTimeSaving(false);
    }
  };

  const handleTimezoneBlur = async (tz: string) => {
    if (!tz) return;
    try {
      await updateNotificationSettings({ briefing_timezone: tz });
    } catch {
      // non-critical
    }
  };

  const enablePush = async () => {
    if (window.electronAPI) {
      try {
        await updateNotificationSettings({ push_enabled: true });
      } catch {
        // best-effort
      }
      setPushEnabled(true);
      setPushState('subscribed');
      return;
    }

    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      setPushState('unavailable');
      return;
    }

    setPushState('requesting');
    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        setPushState('denied');
        return;
      }

      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey ?? ''),
      });

      const rawKey = sub.getKey('p256dh');
      const rawAuth = sub.getKey('auth');
      if (!rawKey || !rawAuth) throw new Error('missing push keys');

      await subscribePush({
        endpoint: sub.endpoint,
        p256dh: btoa(String.fromCharCode(...new Uint8Array(rawKey))),
        auth: btoa(String.fromCharCode(...new Uint8Array(rawAuth))),
      });
      await updateNotificationSettings({ push_enabled: true });
      setPushEnabled(true);
      setPushState('subscribed');
    } catch {
      setPushState('error');
    }
  };

  const disablePush = async () => {
    try {
      await unsubscribePush();
    } catch {
      // best-effort
    }
    try {
      await updateNotificationSettings({ push_enabled: false });
    } catch {
      // best-effort
    }
    setPushEnabled(false);
    setPushState('idle');
  };

  const canEnablePush =
    !pushEnabled &&
    (!!window.electronAPI ||
      (!!vapidKey && 'serviceWorker' in navigator && 'PushManager' in window));

  if (!loaded) return null;

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        Daily Brief
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-4">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-foreground" htmlFor="briefing-time">
            Generation time
          </label>
          <div className="flex items-center gap-2">
            <input
              id="briefing-time"
              type="time"
              value={briefingTime}
              onChange={(e) => setBriefingTime(e.target.value)}
              onBlur={(e) => void handleTimeBlur(e.target.value)}
              className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm tabular-nums focus:outline-none focus:ring-1 focus:ring-ring"
            />
            {timeSaving && <RefreshCw className="size-3 animate-spin text-muted-foreground" />}
          </div>
          <p className="text-[11px] text-muted-foreground">
            Your brief will be generated automatically at this local time each day.
          </p>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-foreground" htmlFor="briefing-timezone">
            Timezone
          </label>
          <input
            id="briefing-timezone"
            type="text"
            value={briefingTimezone}
            onChange={(e) => setBriefingTimezone(e.target.value)}
            onBlur={(e) => void handleTimezoneBlur(e.target.value)}
            placeholder="e.g. Europe/Bucharest"
            className="w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <p className="text-[11px] text-muted-foreground">
            IANA timezone name (e.g. America/New_York). DST is applied automatically.
          </p>
        </div>

        <div className="space-y-2">
          <div className="text-xs font-medium text-foreground">Push notifications</div>
          {pushEnabled ? (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400">
                <Bell className="size-3" />
                Enabled
              </div>
              <button
                onClick={() => void disablePush()}
                className="flex items-center gap-1 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                <BellOff className="size-3" />
                Disable
              </button>
            </div>
          ) : canEnablePush ? (
            <button
              onClick={() => void enablePush()}
              disabled={pushState === 'requesting'}
              className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
            >
              {pushState === 'requesting' ? (
                <RefreshCw className="size-3 animate-spin" />
              ) : (
                <Bell className="size-3" />
              )}
              {pushState === 'requesting' ? 'Requesting…' : 'Enable push notifications'}
            </button>
          ) : !window.electronAPI &&
            (!('serviceWorker' in navigator) || !('PushManager' in window)) ? (
            <p className="text-xs text-muted-foreground">
              Push notifications are not supported in this environment.
            </p>
          ) : null}

          {pushState === 'denied' && (
            <p className="text-xs text-destructive">
              Permission denied. Allow notifications in your browser settings and try again.
            </p>
          )}
          {pushState === 'error' && (
            <p className="text-xs text-destructive">
              Could not set up push notifications. Please try again.
            </p>
          )}
          {!vapidKey && !window.electronAPI && (
            <p className="text-[11px] text-muted-foreground">
              Push notifications require server configuration (VAPID keys).
            </p>
          )}
          <p className="text-[11px] text-muted-foreground">
            You'll receive a notification when your daily brief is ready.
          </p>
        </div>
      </div>
    </section>
  );
}

type ExportState = 'idle' | 'running' | 'done' | 'error';

function DataExportSection() {
  const [state, setState] = useState<ExportState>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleExport = async () => {
    setState('running');
    setErrorMsg(null);
    try {
      await downloadUserExport();
      setState('done');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Export failed.');
      setState('error');
    }
  };

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        Data Export
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <p className="text-xs text-muted-foreground">
          Download a personal archive of your reading history, starred articles, workflow state, and
          daily briefings as a JSON file.
        </p>
        <button
          onClick={() => void handleExport()}
          disabled={state === 'running'}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
        >
          {state === 'running' ? (
            <RefreshCw className="size-3 animate-spin" />
          ) : (
            <Download className="size-3" />
          )}
          {state === 'running' ? 'Preparing…' : 'Download archive'}
        </button>

        {state === 'done' && (
          <p className="text-xs text-green-600 dark:text-green-400">Archive downloaded.</p>
        )}
        {state === 'error' && (
          <p className="text-xs text-destructive">
            {errorMsg ?? 'Export failed. Please try again.'}
          </p>
        )}
      </div>
    </section>
  );
}

export function SettingsPage() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="p-4 md:p-5 max-w-2xl space-y-6">
      <div>
        <h2 className="text-[22px] font-semibold tracking-tight">Settings</h2>
      </div>

      <section>
        <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
          Theme
        </div>
        <div className="grid grid-cols-3 gap-2">
          {THEME_OPTS.map(({ v, label, Icon }) => {
            const active = theme === v;
            return (
              <button
                key={v}
                onClick={() => setTheme(v)}
                className={cn(
                  'flex flex-col items-center gap-1.5 rounded-md border p-3 text-xs font-medium transition-colors',
                  active
                    ? 'border-foreground bg-surface-2'
                    : 'border-border bg-card hover:bg-surface'
                )}
              >
                <Icon className="size-5" />
                {label}
              </button>
            );
          })}
        </div>
      </section>

      <PersonalizationSection />

      <DataExportSection />

      <DailyBriefSection />

      <UpdatesSection />

      <section className="text-xs text-muted-foreground space-y-2">
        <div className="text-[10px] uppercase tracking-wider text-subtle font-medium">About</div>
        <p>Radar is a private technical news triage tool. State is stored on the server.</p>
        <p>
          Press{' '}
          <kbd className="font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
            ?
          </kbd>{' '}
          anywhere for keyboard shortcuts.
        </p>
      </section>
    </div>
  );
}
