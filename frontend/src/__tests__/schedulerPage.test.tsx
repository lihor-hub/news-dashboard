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
  fetchArticleRetention: vi.fn(),
  updateArticleRetention: vi.fn(),
  runArticleRetention: vi.fn(),
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
  apiMock.fetchArticleRetention.mockResolvedValue({
    days: null,
    schedule: '03:30 UTC daily',
    preview: {
      enabled: false,
      retention_days: null,
      eligible_articles: 0,
      protected_articles: 0,
      estimated_payload_bytes: 0,
    },
  });
  apiMock.updateArticleRetention.mockImplementation(async (days: number | null) => ({
    days,
    schedule: '03:30 UTC daily',
    preview: {
      enabled: days !== null,
      retention_days: days,
      eligible_articles: 0,
      protected_articles: 0,
      estimated_payload_bytes: 0,
    },
  }));
  apiMock.runArticleRetention.mockResolvedValue({
    status: 'success',
    deleted_articles: 3,
    protected_articles: 0,
    estimated_deleted_payload_bytes: 2048,
    message: 'deleted 3 articles older than 30 days',
  });
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

  it('labels article retention outcomes', async () => {
    apiMock.fetchLatestJobRuns.mockResolvedValue([
      {
        id: 4,
        job_name: 'article_retention',
        started_at: '2026-09-29T03:30:00Z',
        finished_at: '2026-09-29T03:30:01Z',
        duration_ms: 900,
        status: 'success',
        message: 'deleted 12 articles older than 90 days',
      },
    ]);

    render(<SchedulerPage />);

    expect((await screen.findAllByText('Article retention')).length).toBe(2);
    expect(screen.getByText('deleted 12 articles older than 90 days')).toBeTruthy();
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

describe('SchedulerPage — article retention', () => {
  it('defaults to keep forever and disables manual cleanup', async () => {
    render(<SchedulerPage />);

    expect(await screen.findByRole('heading', { name: 'Article retention' })).toBeTruthy();
    expect(screen.getByRole('combobox', { name: 'Retention policy' })).toHaveValue('forever');
    expect(screen.getByRole('button', { name: 'Run cleanup now' })).toBeDisabled();
    expect(screen.getByText('03:30 UTC daily')).toBeTruthy();
  });

  it('saves numeric retention without running cleanup', async () => {
    render(<SchedulerPage />);
    await screen.findByRole('heading', { name: 'Article retention' });

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'Retention policy' }),
      'custom'
    );
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Retention days' }), '90');
    await userEvent.click(screen.getByRole('button', { name: 'Save retention' }));

    await waitFor(() => expect(apiMock.updateArticleRetention).toHaveBeenCalledWith(90));
    expect(apiMock.runArticleRetention).not.toHaveBeenCalled();
  });

  it('parses scientific notation without truncating it', async () => {
    render(<SchedulerPage />);
    await screen.findByRole('heading', { name: 'Article retention' });
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'Retention policy' }),
      'custom'
    );
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Retention days' }), '1e3');
    await userEvent.click(screen.getByRole('button', { name: 'Save retention' }));

    await waitFor(() => expect(apiMock.updateArticleRetention).toHaveBeenCalledWith(1000));
  });

  it('rejects fractional retention values', async () => {
    render(<SchedulerPage />);
    await screen.findByRole('heading', { name: 'Article retention' });
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'Retention policy' }),
      'custom'
    );
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Retention days' }), '30.9');
    await userEvent.click(screen.getByRole('button', { name: 'Save retention' }));

    expect(apiMock.updateArticleRetention).not.toHaveBeenCalled();
    expect(screen.getByText(/whole number/i)).toBeTruthy();
  });

  it('shows eligible and protected preview counts', async () => {
    apiMock.fetchArticleRetention.mockResolvedValue({
      days: 30,
      schedule: '03:30 UTC daily',
      preview: {
        enabled: true,
        retention_days: 30,
        eligible_articles: 12,
        protected_articles: 4,
        estimated_payload_bytes: 4096,
      },
    });
    render(<SchedulerPage />);

    expect(await screen.findByText('12 eligible')).toBeTruthy();
    expect(screen.getByText('4 protected')).toBeTruthy();
    expect(screen.getByText('4 KB estimated payload')).toBeTruthy();
  });

  it('requires confirmation and supports cancelling cleanup', async () => {
    apiMock.fetchArticleRetention.mockResolvedValue({
      days: 30,
      schedule: '03:30 UTC daily',
      preview: {
        enabled: true,
        retention_days: 30,
        eligible_articles: 12,
        protected_articles: 4,
        estimated_payload_bytes: 4096,
      },
    });
    render(<SchedulerPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Run cleanup now' }));

    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(screen.getByText(/permanently delete 12 eligible articles/i)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(apiMock.runArticleRetention).not.toHaveBeenCalled();
  });

  it('runs confirmed cleanup and refreshes policy and history', async () => {
    apiMock.fetchArticleRetention.mockResolvedValue({
      days: 30,
      schedule: '03:30 UTC daily',
      preview: {
        enabled: true,
        retention_days: 30,
        eligible_articles: 3,
        protected_articles: 0,
        estimated_payload_bytes: 2048,
      },
    });
    render(<SchedulerPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Run cleanup now' }));
    await userEvent.click(screen.getByRole('button', { name: 'Confirm cleanup' }));

    await waitFor(() => expect(apiMock.runArticleRetention).toHaveBeenCalledOnce());
    expect(apiMock.fetchArticleRetention).toHaveBeenCalledTimes(2);
    expect(apiMock.fetchLatestJobRuns).toHaveBeenCalledTimes(2);
  });

  it('shows the reason when cleanup is skipped', async () => {
    apiMock.fetchArticleRetention.mockResolvedValue({
      days: 30,
      schedule: '03:30 UTC daily',
      preview: {
        enabled: true,
        retention_days: 30,
        eligible_articles: 0,
        protected_articles: 0,
        estimated_payload_bytes: 0,
      },
    });
    apiMock.runArticleRetention.mockResolvedValue({
      status: 'skipped',
      deleted_articles: 0,
      protected_articles: 0,
      estimated_deleted_payload_bytes: 0,
      message: 'cleanup already running',
    });
    render(<SchedulerPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Run cleanup now' }));
    await userEvent.click(screen.getByRole('button', { name: 'Confirm cleanup' }));

    expect(await screen.findByText('cleanup already running')).toBeTruthy();
  });

  it('shows retention loading failures without hiding scheduler controls', async () => {
    apiMock.fetchArticleRetention.mockRejectedValue(new Error('retention unavailable'));
    render(<SchedulerPage />);

    expect(await screen.findByText('retention unavailable')).toBeTruthy();
    expect(screen.getByRole('button', { name: '↻ Fetch now' })).toBeTruthy();
  });
});
