// @vitest-environment happy-dom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';

const apiMock = vi.hoisted(() => ({
  askAI: vi.fn(),
  planAgentActions: vi.fn(),
  approveAgentActionRun: vi.fn(),
  cancelAgentActionRun: vi.fn(),
  submitFeedback: vi.fn(),
}));
vi.mock('@/api', () => apiMock);

import { AskPage } from '../pages/AskPage';

afterEach(() => {
  vi.clearAllMocks();
});

function renderPage() {
  return render(
    <MemoryRouter>
      <AskPage />
    </MemoryRouter>
  );
}

function submitQuery(query: string) {
  const textarea = screen.getByPlaceholderText(/postgres listen\/notify/i);
  fireEvent.change(textarea, { target: { value: query } });
  fireEvent.click(screen.getByRole('button', { name: /ask/i }));
}

describe('AskPage agent action plans', () => {
  it('falls back to a normal answer for non-actionable questions', async () => {
    apiMock.planAgentActions.mockResolvedValue({ actionable: false });
    apiMock.askAI.mockResolvedValue({
      answer: 'Postgres LISTEN/NOTIFY is a pub/sub mechanism.',
      sources: [],
      trace_id: null,
    });

    renderPage();
    submitQuery('What did I read about Postgres LISTEN/NOTIFY?');

    await waitFor(() => {
      expect(screen.getByText(/pub\/sub mechanism/)).toBeInTheDocument();
    });
    expect(apiMock.askAI).toHaveBeenCalledWith(
      'What did I read about Postgres LISTEN/NOTIFY?',
      false
    );
  });

  it('shows a proposed plan without mutating anything until approved', async () => {
    apiMock.planAgentActions.mockResolvedValue({
      actionable: true,
      run_id: 7,
      status: 'proposed',
      steps: [
        {
          id: 1,
          run_id: 7,
          ordinal: 0,
          tool: 'archive_article',
          article_id: 3,
          article_title: 'K8s news',
          status: 'pending',
          result_summary: null,
        },
      ],
    });

    renderPage();
    submitQuery('archive the kubernetes story');

    await waitFor(() => {
      expect(screen.getByText('Proposed actions')).toBeInTheDocument();
    });
    expect(screen.getByText('Archive')).toBeInTheDocument();
    expect(screen.getByText(/K8s news/)).toBeInTheDocument();
    expect(apiMock.approveAgentActionRun).not.toHaveBeenCalled();
    expect(apiMock.cancelAgentActionRun).not.toHaveBeenCalled();
  });

  it('approving a plan executes it and renders per-step results', async () => {
    apiMock.planAgentActions.mockResolvedValue({
      actionable: true,
      run_id: 7,
      status: 'proposed',
      steps: [
        {
          id: 1,
          run_id: 7,
          ordinal: 0,
          tool: 'archive_article',
          article_id: 3,
          article_title: 'K8s news',
          status: 'pending',
          result_summary: null,
        },
      ],
    });
    apiMock.approveAgentActionRun.mockResolvedValue({
      id: 7,
      user_id: 1,
      query: 'archive the kubernetes story',
      status: 'executed',
      created_at: '',
      updated_at: '',
      steps: [
        {
          id: 1,
          run_id: 7,
          ordinal: 0,
          tool: 'archive_article',
          article_id: 3,
          article_title: 'K8s news',
          status: 'executed',
          result_summary: 'archive_article applied to article 3',
        },
      ],
    });

    renderPage();
    submitQuery('archive the kubernetes story');
    await waitFor(() => screen.getByText('Proposed actions'));

    fireEvent.click(screen.getByRole('button', { name: /approve/i }));

    await waitFor(() => {
      expect(screen.getByText('Actions completed')).toBeInTheDocument();
    });
    expect(apiMock.approveAgentActionRun).toHaveBeenCalledWith(7);
    expect(screen.queryByText('Proposed actions')).not.toBeInTheDocument();
  });

  it('cancelling a plan records it as cancelled and performs no mutation', async () => {
    apiMock.planAgentActions.mockResolvedValue({
      actionable: true,
      run_id: 9,
      status: 'proposed',
      steps: [
        {
          id: 2,
          run_id: 9,
          ordinal: 0,
          tool: 'star_article',
          article_id: 5,
          article_title: 'AI story',
          status: 'pending',
          result_summary: null,
        },
      ],
    });
    apiMock.cancelAgentActionRun.mockResolvedValue({
      id: 9,
      user_id: 1,
      query: 'star it',
      status: 'cancelled',
      created_at: '',
      updated_at: '',
      steps: [
        {
          id: 2,
          run_id: 9,
          ordinal: 0,
          tool: 'star_article',
          article_id: 5,
          article_title: 'AI story',
          status: 'pending',
          result_summary: null,
        },
      ],
    });

    renderPage();
    submitQuery('star it');
    await waitFor(() => screen.getByText('Proposed actions'));

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));

    await waitFor(() => {
      expect(screen.getByText(/Plan cancelled/)).toBeInTheDocument();
    });
    expect(apiMock.cancelAgentActionRun).toHaveBeenCalledWith(9);
  });

  it('shows a per-step failure summary when approval partially fails', async () => {
    apiMock.planAgentActions.mockResolvedValue({
      actionable: true,
      run_id: 11,
      status: 'proposed',
      steps: [
        {
          id: 3,
          run_id: 11,
          ordinal: 0,
          tool: 'star_article',
          article_id: 4,
          article_title: 'Story A',
          status: 'pending',
          result_summary: null,
        },
        {
          id: 4,
          run_id: 11,
          ordinal: 1,
          tool: 'skip_article',
          article_id: 4,
          article_title: 'Story A',
          status: 'pending',
          result_summary: null,
        },
      ],
    });
    apiMock.approveAgentActionRun.mockResolvedValue({
      id: 11,
      user_id: 1,
      query: 'star then skip',
      status: 'failed',
      created_at: '',
      updated_at: '',
      steps: [
        {
          id: 3,
          run_id: 11,
          ordinal: 0,
          tool: 'star_article',
          article_id: 4,
          article_title: 'Story A',
          status: 'executed',
          result_summary: 'star_article applied to article 4',
        },
        {
          id: 4,
          run_id: 11,
          ordinal: 1,
          tool: 'skip_article',
          article_id: 4,
          article_title: 'Story A',
          status: 'failed',
          result_summary: 'starred articles cannot be skipped',
        },
      ],
    });

    renderPage();
    submitQuery('star then skip it');
    await waitFor(() => screen.getByText('Proposed actions'));
    fireEvent.click(screen.getByRole('button', { name: /approve/i }));

    await waitFor(() => {
      expect(screen.getByText('Some actions failed')).toBeInTheDocument();
    });
    expect(screen.getByText('starred articles cannot be skipped')).toBeInTheDocument();
  });
});
