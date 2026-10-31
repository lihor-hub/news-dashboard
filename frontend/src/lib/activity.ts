import { fetchAnalyticsSettings } from '@/api';
import { openActivityWindow, sendActivityHeartbeat, type ActivityWindow } from '@/api/activity';

export const stopActivity = () => window.dispatchEvent(new Event('activity-stop'));
export const pauseActivity = () => window.dispatchEvent(new Event('activity-pause'));
export const refreshActivityConsent = () => window.dispatchEvent(new Event('activity-consent'));

/** One in-memory recorder per protected account mount. No offline queue or article evidence. */
export function startActivity(onAccepted: () => void) {
  let stopped = false;
  let generation = 0;
  let consentGeneration = 0;
  let allowed = false;
  let busy = false;
  let lease: ActivityWindow | null = null;
  let baseline = performance.now();
  let lastTick = baseline;
  let lastWall = Date.now();
  let idleUntil = baseline + 300000;
  let nextAttempt = baseline;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;
  const foreground = () =>
    document.visibilityState === 'visible' && document.hasFocus() && navigator.onLine;
  let wasForeground = foreground();
  const eligible = () => !stopped && allowed && foreground() && performance.now() < idleUntil;

  function discard() {
    generation++;
    lease = null;
    busy = false;
    clearTimeout(retryTimer);
  }
  async function loadConsent() {
    discard();
    allowed = false;
    const gen = ++consentGeneration;
    try {
      const consent = await fetchAnalyticsSettings();
      if (!stopped && gen === consentGeneration)
        allowed = consent.enabled && consent.global_enabled;
    } catch {
      /* Unknown consent fails closed. */
    }
  }
  async function open() {
    busy = true;
    const gen = generation;
    try {
      const result = await openActivityWindow();
      if (stopped || gen !== generation || !eligible()) return;
      if (result.available) {
        lease = result;
        baseline = performance.now();
      } else {
        allowed = false;
      }
    } catch {
      nextAttempt = performance.now() + 15000;
    } finally {
      if (gen === generation) busy = false;
    }
  }
  function flush(final = false) {
    const current = lease;
    lease = null;
    if (!current || !navigator.onLine) return;
    const end = Math.floor(Math.min(performance.now(), idleUntil) - baseline);
    if (end <= 0 || end >= 30000) return;
    busy = true;
    const gen = generation;
    const body = { window_id: current.window_id, start_ms: 0, end_ms: end };
    async function send(retry: boolean) {
      try {
        const result = await sendActivityHeartbeat(body, final);
        if (gen !== generation || stopped) return;
        if (result.available) onAccepted();
        else allowed = false;
      } catch {
        if (retry && !final && gen === generation && eligible()) {
          retryTimer = setTimeout(() => void send(false), 1000);
          return;
        }
      }
      if (gen === generation) busy = false;
    }
    void send(true);
  }
  function tick() {
    const now = performance.now();
    const wall = Date.now();
    if (now - lastTick > 30000 || Math.abs(wall - lastWall - (now - lastTick)) > 2000) discard();
    lastTick = now;
    lastWall = wall;
    const present = foreground();
    if (present && !wasForeground) idleUntil = now + 300000;
    wasForeground = present;
    if (!eligible()) {
      if (lease) flush(true);
      return;
    }
    if (lease && now - baseline >= 15000) flush();
    else if (!lease && !busy && now >= nextAttempt) void open();
  }
  function pause() {
    if (lease) flush(true);
    // An issuance that resolves after a background transition must never start a lease.
    discard();
  }
  function resume() {
    pause();
    lastTick = performance.now();
    lastWall = Date.now();
    if (foreground()) {
      idleUntil = lastTick + 300000;
      if (!allowed && !stopped) void loadConsent();
    }
  }
  function interaction(event: Event) {
    if (event.isTrusted && foreground()) idleUntil = performance.now() + 300000;
  }
  function suspendConsent() {
    consentGeneration++;
    allowed = false;
    discard();
  }
  function stop() {
    stopped = true;
    suspendConsent(); // Logout cannot send a final interval under the next account's cookie.
  }
  function visibility() {
    if (foreground()) resume();
    else pause();
  }
  // Programmatic scrolling also emits trusted scroll events; only direct input resets idle.
  const inputs = ['pointerdown', 'pointermove', 'keydown', 'touchstart', 'touchmove', 'wheel'];
  inputs.forEach((name) =>
    document.addEventListener(name, interaction, { passive: true, capture: true })
  );
  window.addEventListener('blur', pause);
  window.addEventListener('focus', resume);
  window.addEventListener('pagehide', pause);
  window.addEventListener('pageshow', resume);
  window.addEventListener('offline', pause);
  window.addEventListener('online', resume);
  window.addEventListener('activity-pause', suspendConsent);
  window.addEventListener('activity-stop', stop);
  window.addEventListener('activity-consent', loadConsent);
  document.addEventListener('visibilitychange', visibility);
  const timer = setInterval(tick, 250);
  void loadConsent();
  return () => {
    stop();
    clearInterval(timer);
    inputs.forEach((name) => document.removeEventListener(name, interaction, true));
    window.removeEventListener('blur', pause);
    window.removeEventListener('focus', resume);
    window.removeEventListener('pagehide', pause);
    window.removeEventListener('pageshow', resume);
    window.removeEventListener('offline', pause);
    window.removeEventListener('online', resume);
    window.removeEventListener('activity-pause', suspendConsent);
    window.removeEventListener('activity-stop', stop);
    window.removeEventListener('activity-consent', loadConsent);
    document.removeEventListener('visibilitychange', visibility);
  };
}
