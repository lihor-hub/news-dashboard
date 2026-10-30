// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useQualifyingRead } from '@/hooks/useQualifyingRead';
import * as core from '@/api/core';
import * as settings from '@/api/settings';

const account = { id: 42, is_guest: false };
vi.mock('@/contexts/auth', () => ({ useAuth: () => ({ user: account }) }));

let body: HTMLDivElement;
let cache: QueryClient;
let focused = true;
let bodyBottom = 200;

beforeEach(() => {
  vi.useFakeTimers();
  body = document.createElement('div');
  body.style.visibility = 'visible';
  document.body.append(body);
  vi.spyOn(body, 'getBoundingClientRect').mockImplementation(() => ({
    top: 100,
    bottom: bodyBottom,
    height: bodyBottom - 100,
    left: 0,
    right: 500,
    width: 500,
    x: 0,
    y: 100,
    toJSON: () => ({}),
  }));
  focused = true;
  bodyBottom = 200;
  vi.spyOn(document, 'hasFocus').mockImplementation(() => focused);
  vi.stubGlobal('crypto', { subtle: { digest: vi.fn().mockResolvedValue(new ArrayBuffer(32)) } });
  vi.spyOn(settings, 'fetchAnalyticsSettings').mockResolvedValue({
    enabled: true,
    global_enabled: true,
  });
  vi.spyOn(core, 'requestJson').mockResolvedValue({
    available: true,
    token: 'lease',
    sequence: 0,
    required_ms: 30000,
    credited: false,
  });
  cache = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});
afterEach(() => {
  body.remove();
  cache.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={cache}>{children}</QueryClientProvider>;
}
async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}
function mount(text: string | undefined) {
  const ref = { current: body };
  return renderHook(({ content }) => useQualifyingRead('7', content, ref), {
    initialProps: { content: text },
    wrapper,
  });
}

describe('separate loaded-body evidence', () => {
  it('refreshes the collection but not the active list when automatic completion wins', async () => {
    const invalidate = vi.spyOn(cache, 'invalidateQueries');
    vi.mocked(core.requestJson)
      .mockResolvedValueOnce({
        available: true,
        token: 'lease',
        sequence: 0,
        required_ms: 30000,
        credited: false,
      })
      .mockResolvedValueOnce({
        available: true,
        token: 'lease',
        sequence: 1,
        required_ms: 30000,
        credited: true,
      });
    mount('Loaded body');
    await advance(10250);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['progress-rewards', 42] });
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: ['articles'] });
  });

  it('pauses at the five-minute idle boundary and resumes only after interaction', async () => {
    mount('Loaded body');
    await advance(300000);
    const sent = vi.mocked(core.requestJson).mock.calls.length;
    await advance(20000);
    expect(core.requestJson).toHaveBeenCalledTimes(sent);
    window.dispatchEvent(new Event('scroll'));
    await advance(250);
    expect(core.requestJson).toHaveBeenCalledTimes(sent + 1);
  });

  it('opening starts a lease with no evidence; a fully visible short body still needs attentive time', async () => {
    mount('A loaded body');
    await advance(250);
    expect(core.requestJson).toHaveBeenCalledTimes(1);
    const start = JSON.parse(vi.mocked(core.requestJson).mock.calls[0][1]!.body as string);
    expect(start).toEqual({ body_version: '0'.repeat(64) });
    await advance(10000);
    const heartbeat = JSON.parse(vi.mocked(core.requestJson).mock.calls[1][1]!.body as string);
    expect(heartbeat.progress).toBe(1);
    expect(heartbeat.attentive_ms).toBeGreaterThanOrEqual(9750);
    expect(heartbeat.attentive_ms).toBeLessThanOrEqual(10000);
    expect(heartbeat.end_ms).toBe(heartbeat.attentive_ms);
  });
  it('excludes blur and hidden-body time, and resets the lease when the loaded body changes', async () => {
    const hook = mount('A loaded body');
    await advance(250);
    focused = false;
    await advance(15000);
    expect(core.requestJson).toHaveBeenCalledTimes(1);
    focused = true;
    bodyBottom = 100;
    await advance(5000);
    expect(core.requestJson).toHaveBeenCalledTimes(1);
    bodyBottom = 200;
    await advance(250);
    const heartbeat = JSON.parse(vi.mocked(core.requestJson).mock.calls[1][1]!.body as string);
    expect(heartbeat.attentive_ms).toBeLessThanOrEqual(250);
    hook.rerender({ content: 'Replacement body' });
    await advance(250);
    const replacement = JSON.parse(
      vi.mocked(core.requestJson).mock.calls.at(-1)![1]!.body as string
    );
    expect(replacement.token).toBeUndefined();
  });
  it('does not send summary/loading evidence or send without consent', async () => {
    const hook = mount(undefined);
    await advance(11000);
    expect(core.requestJson).not.toHaveBeenCalled();
    vi.mocked(settings.fetchAnalyticsSettings).mockResolvedValue({
      enabled: false,
      global_enabled: true,
    });
    hook.rerender({ content: 'Loaded article body' });
    await advance(11000);
    expect(core.requestJson).not.toHaveBeenCalled();
  });
});
