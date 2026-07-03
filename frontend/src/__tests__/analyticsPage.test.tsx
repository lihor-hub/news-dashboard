// @vitest-environment happy-dom
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMock = vi.hoisted(() => ({
  fetchAdminAnalytics: vi.fn(),
  fetchAdminAiQuality: vi.fn(),
}));
vi.mock('../api', () => apiMock);

import { AnalyticsPage } from '../pages/AnalyticsPage';

const analytics = {
  range_days: 30,
  generated_at: '2026-07-03T00:00:00Z',
  summary: {
    dau: 1,
    wau: 2,
    mau: 3,
    stickiness: 0.33,
    total_minutes: 12,
    total_sessions: 4,
    avg_session_minutes: 3,
    total_reads: 5,
    total_events: 6,
  },
  active_over_time: [],
  users: [],
  route_popularity: [],
  feature_usage: [],
  article_dwell: [],
  category_consumption: [],
  source_consumption: [],
  hourly_heatmap: [],
  skip_rate_trend: [],
  recommendation_funnel: { recommended: 0, read: 0, skipped: 0 },
};

describe('AnalyticsPage AI quality panel', () => {
  beforeEach(() => {
    apiMock.fetchAdminAnalytics.mockResolvedValue(analytics);
    apiMock.fetchAdminAiQuality.mockResolvedValue({
      range_days: 30,
      feedback: [{ feature: 'ask-ai', total: 3, positive: 2, negative: 1 }],
      evals: [{ feature: 'ask-ai', runs: 1, total: 4, passed: 3, failed: 1, pass_rate: 0.75 }],
      recent_failures: [
        {
          feature: 'ask-ai',
          example_id: 7,
          failure_reason: 'unknown citations',
          created_at: '2026-07-03T00:00:00Z',
        },
      ],
    });
  });

  it('renders local feedback and eval pass rate', async () => {
    render(<AnalyticsPage />);

    expect(await screen.findByText('AI quality')).toBeTruthy();
    expect(screen.getByText('75%')).toBeTruthy();
    expect(screen.getByText('2 up / 1 down')).toBeTruthy();
    expect(screen.getByText('unknown citations')).toBeTruthy();
  });
});
