// @vitest-environment happy-dom
import { afterEach, expect, it, vi } from 'vitest';
import {
  acknowledgeRewardGroup,
  claimDailyWelcome,
  claimPresentation,
  claimRewardGroup,
} from '@/api/progress';

afterEach(() => vi.unstubAllGlobals());

it('posts exact presentation targets, including explicit null-date history mode', async () => {
  const envelope = { show: false, reason: 'already_consumed' };
  const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify(envelope)));
  vi.stubGlobal('fetch', fetch);
  expect(await claimDailyWelcome('2026-01-10', 'history-1')).toEqual(envelope);
  await claimPresentation(null, 'history-2');
  await claimDailyWelcome('2026-01-11');
  expect(fetch.mock.calls.map(([url, init]) => [url, init.method, JSON.parse(init.body)])).toEqual([
    [
      '/api/users/me/presentation/claim',
      'POST',
      { expected_visit_date: '2026-01-10', historical_group_id: 'history-1' },
    ],
    [
      '/api/users/me/presentation/claim',
      'POST',
      { expected_visit_date: null, historical_group_id: 'history-2' },
    ],
    ['/api/users/me/presentation/claim', 'POST', { expected_visit_date: '2026-01-11' }],
  ]);
});

it('encodes the exact reward claim and ACK target without changing a losing response', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ show: false, reason: 'already_consumed' }))
    )
    .mockResolvedValueOnce(new Response(JSON.stringify({ acknowledged: true })));
  vi.stubGlobal('fetch', fetch);
  expect(await claimRewardGroup('group/?#&')).toEqual({ show: false, reason: 'already_consumed' });
  expect(await acknowledgeRewardGroup('group/?#&')).toEqual({ acknowledged: true });
  expect(fetch.mock.calls.map(([url, init]) => [url, init.method, init.body])).toEqual([
    ['/api/users/me/reward-events/group%2F%3F%23%26/claim', 'POST', '{}'],
    ['/api/users/me/reward-events/group%2F%3F%23%26/ack', 'POST', '{}'],
  ]);
});
