import { useEffect } from 'react';
import { fetchLatestBriefing, fetchNotificationSettings } from '@/api';

const LAST_NOTIFIED_KEY = 'nd_electron_last_brief_id';
const POLL_INTERVAL_MS = 5 * 60 * 1000;

/**
 * Polls for new daily briefings while the Electron app is open.
 * Fires a native OS notification the first time a new complete briefing appears.
 * Each briefing ID is notified at most once (tracked in localStorage).
 *
 * Must only be called when the user is authenticated (AppShell context).
 */
export function useElectronBriefNotifier(navigate: (path: string) => void): void {
  useEffect(() => {
    if (!window.electronAPI) return;

    window.electronAPI.onNotificationClick((url) => navigate(url));

    let active = true;

    async function poll() {
      if (!active) return;
      try {
        const settings = await fetchNotificationSettings();
        if (!settings.push_enabled) return;

        const latest = await fetchLatestBriefing();
        if (!('id' in latest) || latest.status !== 'complete') return;

        const lastId = localStorage.getItem(LAST_NOTIFIED_KEY);
        if (lastId === String(latest.id)) return;

        localStorage.setItem(LAST_NOTIFIED_KEY, String(latest.id));
        window.electronAPI!.showNotification(
          latest.title,
          latest.summary ?? '',
          `/briefs/${latest.id}`
        );
      } catch {
        // non-critical — silent fail
      }
    }

    void poll();
    const timer = setInterval(() => void poll(), POLL_INTERVAL_MS);

    return () => {
      active = false;
      clearInterval(timer);
      window.electronAPI?.removeNotificationClickListener();
    };
  }, [navigate]);
}
