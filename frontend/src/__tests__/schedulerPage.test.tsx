// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const apiMock = vi.hoisted(() => ({
  fetchSchedulerStatus: vi.fn(),
  fetchLatestJobRuns: vi.fn(),
  setSchedulerInterval: vi.fn(),
  pauseScheduler: vi.fn(),
  resumeScheduler: vi.fn(),
  ingestNow: vi.fn(),
  runEmbeddingDedup: vi.fn(),
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
  apiMock.runEmbeddingDedup.mockResolvedValue({ status: 'success', embedded: 0, merged: 0 });
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

describe('SchedulerPage — manual duplicate cleanup', () => {
  it('runs duplicate cleanup and refreshes job history', async () => {
    apiMock.runEmbeddingDedup.mockResolvedValue({ status: 'success', embedded: 4, merged: 2 });
    render(<SchedulerPage />);

    await userEvent.click(await screen.findByRole('button', { name: 'Remove duplicates' }));

    await waitFor(() => expect(apiMock.runEmbeddingDedup).toHaveBeenCalledOnce());
    expect(apiMock.fetchLatestJobRuns).toHaveBeenCalledTimes(2);
    expect(await screen.findByText('Remove duplicates')).toBeTruthy();
  });

  it('shows a pending label while duplicate cleanup is running', async () => {
    let resolveRun: (value: { status: 'success'; embedded: number; merged: number }) => void;
    apiMock.runEmbeddingDedup.mockReturnValue(
      new Promise((resolve) => {
        resolveRun = resolve;
      })
    );
    render(<SchedulerPage />);

    await userEvent.click(await screen.findByRole('button', { name: 'Remove duplicates' }));

    expect(screen.getByRole('button', { name: 'Removing duplicates...' })).toBeDisabled();
    resolveRun!({ status: 'success', embedded: 0, merged: 0 });
  });

  it('keeps duplicate cleanup available while ingest is running', async () => {
    apiMock.ingestNow.mockReturnValue(new Promise(() => undefined));
    render(<SchedulerPage />);

    await userEvent.click(await screen.findByRole('button', { name: '↻ Fetch now' }));

    expect(screen.getByRole('button', { name: 'Remove duplicates' })).not.toBeDisabled();
  });
});
