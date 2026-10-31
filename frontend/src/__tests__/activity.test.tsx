import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fetchAnalyticsSettings } from '@/api';
import { fetchActivity, openActivityWindow, sendActivityHeartbeat } from '@/api/activity';
import { pauseActivity, refreshActivityConsent, startActivity, stopActivity } from '@/lib/activity';
import { ActivityProgress } from '@/components/ActivityProgress';
import { activeDuration } from '@/lib/format';

vi.mock('@/api', () => ({ fetchAnalyticsSettings: vi.fn() }));
vi.mock('@/api/activity', () => ({
  fetchActivity: vi.fn(),
  openActivityWindow: vi.fn(),
  sendActivityHeartbeat: vi.fn(),
}));
const consent = vi.mocked(fetchAnalyticsSettings);
const open = vi.mocked(openActivityWindow);
const send = vi.mocked(sendActivityHeartbeat);
let focused = true;
let visible = true;
let connected = true;
let cleanup: (() => void) | undefined;

beforeEach(() => {
  vi.useFakeTimers({
    toFake: ['setInterval', 'clearInterval', 'setTimeout', 'clearTimeout', 'Date', 'performance'],
  });
  vi.setSystemTime(new Date('2026-01-01T12:00:00Z'));
  focused = visible = connected = true;
  vi.spyOn(document, 'hasFocus').mockImplementation(() => focused);
  vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() =>
    visible ? 'visible' : 'hidden'
  );
  vi.spyOn(navigator, 'onLine', 'get').mockImplementation(() => connected);
  consent.mockResolvedValue({ enabled: true, global_enabled: true });
  open.mockResolvedValue({ available: true, window_id: 'window', duration_ms: 30000 });
  send.mockResolvedValue({ available: true } as Awaited<ReturnType<typeof sendActivityHeartbeat>>);
});
afterEach(() => {
  cleanup?.();
  cleanup = undefined;
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});
const advance = (ms: number) => vi.advanceTimersByTimeAsync(ms);
const total = () => send.mock.calls.reduce((sum, [body]) => sum + body.end_ms - body.start_ms, 0);

describe('account-scoped activity recorder', () => {
  it('clips the final quiet interval at 299999/300000/300001ms exactly', async () => {
    cleanup = startActivity(vi.fn());
    await advance(299999);
    const before = total();
    await advance(1);
    expect(send.mock.calls.at(-1)?.[0].end_ms).toBe(10000);
    expect(total() - before).toBe(10000);
    await advance(1);
    expect(total()).toBe(before + 10000);
    await advance(60000);
    expect(total()).toBe(before + 10000);
  });
  it('counts quiet focused connected use, clips exactly at idle deadline, never catches up', async () => {
    cleanup = startActivity(vi.fn());
    await advance(300000);
    const recorded = total();
    expect(recorded).toBeGreaterThan(280000);
    expect(recorded).toBeLessThanOrEqual(300000);
    await advance(600000);
    expect(total()).toBe(recorded);
    // Scripted events are not user activity.
    document.dispatchEvent(new Event('pointerdown'));
    await advance(20000);
    expect(total()).toBe(recorded);
    window.dispatchEvent(new Event('focus'));
    await advance(16000);
    expect(total()).toBeGreaterThan(recorded);
  });
  it('does not issue hidden/unfocused/offline and resumes at a new zero baseline', async () => {
    visible = false;
    cleanup = startActivity(vi.fn());
    await advance(60000);
    expect(open).not.toHaveBeenCalled();
    visible = true;
    focused = false;
    document.dispatchEvent(new Event('visibilitychange'));
    await advance(60000);
    expect(open).not.toHaveBeenCalled();
    focused = true;
    window.dispatchEvent(new Event('focus'));
    await advance(16000);
    expect(total()).toBe(15000);
    connected = false;
    window.dispatchEvent(new Event('offline'));
    const before = total();
    await advance(600000);
    expect(total()).toBe(before);
    connected = true;
    window.dispatchEvent(new Event('online'));
    await advance(16000);
    expect(total() - before).toBe(15000);
  });
  it('flushes a bounded tail on blur/pagehide, with keepalive, no background growth', async () => {
    cleanup = startActivity(vi.fn());
    await advance(5250);
    focused = false;
    window.dispatchEvent(new Event('blur'));
    expect(total()).toBe(5000);
    expect(send.mock.calls[0][1]).toBe(true);
    await advance(60000);
    expect(total()).toBe(5000);
    focused = true;
    window.dispatchEvent(new Event('pageshow'));
    await advance(5250);
    visible = false;
    window.dispatchEvent(new Event('pagehide'));
    expect(total()).toBe(10000);
  });
  it('drops suspend/wall discontinuities instead of converting them to time', async () => {
    cleanup = startActivity(vi.fn());
    await advance(5250);
    vi.setSystemTime(Date.now() + 3600000);
    await advance(16000);
    expect(send.mock.calls.every(([b]) => b.end_ms <= 15250)).toBe(true);
    expect(total()).toBeLessThan(20000);
  });
  it('retries the identical payload after loss without anchoring a returned lease', async () => {
    send.mockRejectedValueOnce(new Error('lost response'));
    cleanup = startActivity(vi.fn());
    await advance(16500);
    expect(send).toHaveBeenCalledTimes(2);
    expect(send.mock.calls[0][0]).toEqual(send.mock.calls[1][0]);
    expect(open).toHaveBeenCalledTimes(2);
  });
  it('fences delayed issuance/retry/logout and clears StrictMode mounts', async () => {
    let resolve!: (value: Awaited<ReturnType<typeof openActivityWindow>>) => void;
    open.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        })
    );
    const accepted = vi.fn();
    cleanup = startActivity(accepted);
    await advance(250);
    stopActivity();
    resolve({ available: true, window_id: 'old-account', duration_ms: 30000 });
    await advance(60000);
    expect(send).not.toHaveBeenCalled();
    cleanup();
    cleanup = startActivity(accepted);
    await advance(16000);
    expect(send).toHaveBeenCalledTimes(1);
    expect(accepted).toHaveBeenCalledTimes(1);
  });
  it('does not lose a pending consent response on focus/visibility transitions', async () => {
    let resolve!: (value: Awaited<ReturnType<typeof fetchAnalyticsSettings>>) => void;
    consent.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        })
    );
    cleanup = startActivity(vi.fn());
    focused = false;
    window.dispatchEvent(new Event('blur'));
    focused = true;
    window.dispatchEvent(new Event('focus'));
    resolve({ enabled: true, global_enabled: true });
    await advance(16000);
    expect(send).toHaveBeenCalledTimes(1);
  });
  it('fails closed on consent errors and can pause/refresh without reviving logout', async () => {
    consent.mockRejectedValueOnce(new Error('failed'));
    cleanup = startActivity(vi.fn());
    await advance(16000);
    expect(open).not.toHaveBeenCalled();
    refreshActivityConsent();
    await advance(16000);
    expect(send).toHaveBeenCalledTimes(1);
    pauseActivity();
    await advance(60000);
    expect(send).toHaveBeenCalledTimes(1);
    refreshActivityConsent();
    await advance(16000);
    expect(send).toHaveBeenCalledTimes(2);
    stopActivity();
    refreshActivityConsent();
    await advance(16000);
    expect(send).toHaveBeenCalledTimes(2);
  });
});

describe('active-time home', () => {
  it('shows an actionable error, not a successful zero', async () => {
    vi.useRealTimers();
    vi.mocked(fetchActivity).mockRejectedValueOnce(new Error('offline'));
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <ActivityProgress accountId={2} />
      </QueryClientProvider>
    );
    expect(await screen.findByText(/Active time is unavailable/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry active time' })).toBeInTheDocument();
  });
  it('formats minutes conservatively with readable units', () => {
    expect(activeDuration(59999)).toBe('0 minutes');
    expect(activeDuration(900000)).toBe('15 minutes');
    expect(activeDuration(3600000)).toBe('1h 0m');
    expect(activeDuration(72000000)).toBe('20h 0m');
  });
  it('labels unknown zero/disabled coverage rather than complete lifetime time', async () => {
    vi.useRealTimers();
    vi.mocked(fetchActivity).mockResolvedValue({
      available: true,
      measurement_enabled: false,
      total_ms: 0,
      measured_since: null,
      approximate: true,
      coverage: { status: 'unknown', reasons: ['global_gap_or_unknown', 'pre_measurement'] },
      next_target_ms: 900000,
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ActivityProgress accountId={1} />
      </QueryClientProvider>
    );
    expect(await screen.findByText(/not a complete lifetime zero/)).toBeInTheDocument();
    expect(screen.getByText(/Measurement is disabled/)).toBeInTheDocument();
    expect(screen.getByText(/Next time badge: 15 minutes/)).toBeInTheDocument();
    expect(screen.getByText(/Coverage incomplete \(unknown\)/)).toBeInTheDocument();
  });
});
