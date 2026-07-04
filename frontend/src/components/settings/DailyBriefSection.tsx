import { useEffect, useState } from 'react';
import { RefreshCw, Bell, BellOff } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  fetchNotificationSettings,
  subscribePush,
  unsubscribePush,
  updateNotificationSettings,
} from '@/api';

function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  return new Uint8Array([...raw].map((c) => c.charCodeAt(0)));
}

function arrayBufferToBase64Url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  const standard = btoa(String.fromCharCode(...bytes));
  return standard.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

type PushState = 'idle' | 'requesting' | 'subscribed' | 'denied' | 'unavailable' | 'error';
type TimezoneSaveState = 'idle' | 'saving' | 'saved' | 'error';

const FALLBACK_TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Bucharest',
  'Asia/Tokyo',
  'Australia/Sydney',
];

function getSupportedTimezones(): string[] {
  const intlWithSupportedValues = Intl as typeof Intl & {
    supportedValuesOf?: (key: 'timeZone') => string[];
  };
  return intlWithSupportedValues.supportedValuesOf?.('timeZone') ?? FALLBACK_TIMEZONES;
}

export function DailyBriefSection() {
  const [briefingTime, setBriefingTime] = useState('09:00');
  const [briefingTimezone, setBriefingTimezone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone
  );
  const [savedBriefingTimezone, setSavedBriefingTimezone] = useState(briefingTimezone);
  const [timezoneSaveState, setTimezoneSaveState] = useState<TimezoneSaveState>('idle');
  const [timezoneError, setTimezoneError] = useState<string | null>(null);
  const [pushEnabled, setPushEnabled] = useState(false);
  const [vapidKey, setVapidKey] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [timeSaving, setTimeSaving] = useState(false);
  const [pushState, setPushState] = useState<PushState>('idle');
  const [supportedTimezones] = useState(getSupportedTimezones);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const s = await fetchNotificationSettings();
        if (!cancelled) {
          setBriefingTime(s.briefing_time);
          const loadedTimezone =
            s.briefing_timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
          setBriefingTimezone(loadedTimezone);
          setSavedBriefingTimezone(loadedTimezone);
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
    const normalizedTimezone = tz.trim();
    if (!normalizedTimezone) return;
    if (normalizedTimezone === savedBriefingTimezone) {
      setTimezoneSaveState('idle');
      setTimezoneError(null);
      return;
    }
    setBriefingTimezone(normalizedTimezone);
    setTimezoneSaveState('saving');
    setTimezoneError(null);
    try {
      await updateNotificationSettings({ briefing_timezone: normalizedTimezone });
      setSavedBriefingTimezone(normalizedTimezone);
      setTimezoneSaveState('saved');
    } catch {
      setTimezoneSaveState('error');
      setTimezoneError('Unknown timezone. Choose a valid IANA timezone.');
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
        p256dh: arrayBufferToBase64Url(rawKey),
        auth: arrayBufferToBase64Url(rawAuth),
      });
      await updateNotificationSettings({ push_enabled: true });
      setPushEnabled(true);
      setPushState('subscribed');
    } catch {
      setPushState('error');
    }
  };

  const disablePush = async () => {
    let subscription: PushSubscription | null = null;
    try {
      if (!window.electronAPI && 'serviceWorker' in navigator && 'PushManager' in window) {
        const reg = await navigator.serviceWorker.ready;
        subscription = await reg.pushManager.getSubscription();
      }
      await unsubscribePush(subscription?.endpoint);
      await subscription?.unsubscribe();
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
  const timezoneDescriptionIds =
    timezoneSaveState === 'saved' || timezoneError
      ? 'briefing-timezone-help briefing-timezone-status'
      : 'briefing-timezone-help';

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
          <div className="flex items-center gap-2">
            <input
              id="briefing-timezone"
              type="text"
              list="briefing-timezone-options"
              value={briefingTimezone}
              onChange={(e) => {
                setBriefingTimezone(e.target.value);
                setTimezoneSaveState('idle');
                setTimezoneError(null);
              }}
              onBlur={(e) => void handleTimezoneBlur(e.target.value)}
              placeholder="e.g. Europe/Bucharest"
              aria-describedby={timezoneDescriptionIds}
              aria-invalid={timezoneSaveState === 'error'}
              className={cn(
                'w-full rounded-md border bg-surface px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring',
                timezoneSaveState === 'error' ? 'border-destructive' : 'border-border'
              )}
            />
            {timezoneSaveState === 'saving' && (
              <RefreshCw className="size-3 shrink-0 animate-spin text-muted-foreground" />
            )}
            {timezoneSaveState === 'saved' && (
              <span
                id="briefing-timezone-status"
                className="text-xs text-green-600 dark:text-green-400"
              >
                Saved
              </span>
            )}
          </div>
          <datalist id="briefing-timezone-options">
            {supportedTimezones.map((timezone) => (
              <option key={timezone} value={timezone} />
            ))}
          </datalist>
          <p id="briefing-timezone-help" className="text-[11px] text-muted-foreground">
            IANA timezone name (e.g. America/New_York). DST is applied automatically.
          </p>
          {timezoneError && (
            <p id="briefing-timezone-status" className="text-xs text-destructive" role="alert">
              {timezoneError}
            </p>
          )}
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
