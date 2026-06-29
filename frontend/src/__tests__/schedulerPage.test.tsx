// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const apiMock = vi.hoisted(() => ({
  fetchSchedulerStatus: vi.fn(),
  fetchLatestJobRuns: vi.fn(),
  setSchedulerInterval: vi.fn(),
  pauseScheduler: vi.fn(),
  resumeScheduler: vi.fn(),
  ingestNow: vi.fn(),
}));
vi.mock('../api', () => apiMock);

import { SchedulerPage } from '../pages/SchedulerPage';

const defaultStatus = {
  interval_minutes: 30,
  paused: false,
  next_run_at: null,
  interval_ingest_enabled: true,
};

beforeEach(() => {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
  );
  apiMock.fetchSchedulerStatus.mockResolvedValue(defaultStatus);
  apiMock.fetchLatestJobRuns.mockResolvedValue([]);
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe('SchedulerPage — job outcomes section', () => {
  it('hides the job outcomes section when there are no runs', async () => {
    apiMock.fetchLatestJobRuns.mockResolvedValue([]);
    render(<SchedulerPage />);
    await waitFor(() => expect(screen.queryByText('Last Job Outcomes')).toBeNull());
  });

  it('shows a successful job run with correct label and badge', async () => {
    apiMock.fetchLatestJobRuns.mockResolvedValue([
      {
        id: 1,
        job_name: 'digest',
        started_at: '2026-06-01T08:00:00Z',
        finished_at: '2026-06-01T08:00:02Z',
        duration_ms: 2000,
        status: 'success',
        message: null,
      },
    ]);
    render(<SchedulerPage />);
    await waitFor(() => expect(screen.getByText('Last Job Outcomes')).toBeTruthy());
    expect(screen.getByText('Daily digest')).toBeTruthy();
    expect(screen.getByText('success')).toBeTruthy();
    expect(screen.getByText('2000ms')).toBeTruthy();
  });

  it('shows a failed job run with message', async () => {
    apiMock.fetchLatestJobRuns.mockResolvedValue([
      {
        id: 2,
        job_name: 'recommendations',
        started_at: '2026-06-01T07:30:00Z',
        finished_at: '2026-06-01T07:30:05Z',
        duration_ms: 5000,
        status: 'failure',
        message: 'connection refused',
      },
    ]);
    render(<SchedulerPage />);
    await waitFor(() => expect(screen.getByText('failure')).toBeTruthy());
    expect(screen.getByText('Recommendations')).toBeTruthy();
    expect(screen.getByText('connection refused')).toBeTruthy();
  });

  it('shows a skipped job run', async () => {
    apiMock.fetchLatestJobRuns.mockResolvedValue([
      {
        id: 3,
        job_name: 'digest',
        started_at: '2026-06-01T08:00:00Z',
        finished_at: '2026-06-01T08:00:00Z',
        duration_ms: 10,
        status: 'skipped',
        message: 'no DIGEST_TO configured',
      },
    ]);
    render(<SchedulerPage />);
    await waitFor(() => expect(screen.getByText('skipped')).toBeTruthy());
    expect(screen.getByText('no DIGEST_TO configured')).toBeTruthy();
  });

  it('renders multiple job outcomes', async () => {
    apiMock.fetchLatestJobRuns.mockResolvedValue([
      {
        id: 1,
        job_name: 'digest',
        started_at: '2026-06-01T08:00:00Z',
        finished_at: '2026-06-01T08:00:02Z',
        duration_ms: 2000,
        status: 'success',
        message: null,
      },
      {
        id: 2,
        job_name: 'analytics_retention',
        started_at: '2026-06-01T03:00:00Z',
        finished_at: '2026-06-01T03:00:01Z',
        duration_ms: 800,
        status: 'success',
        message: 'pruned 42 events older than 90 days',
      },
    ]);
    render(<SchedulerPage />);
    await waitFor(() => expect(screen.getByText('Daily digest')).toBeTruthy());
    expect(screen.getByText('Analytics retention')).toBeTruthy();
    expect(screen.getByText('pruned 42 events older than 90 days')).toBeTruthy();
  });
});
