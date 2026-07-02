// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ListenQueueProvider, useListenQueue } from '../contexts/listenQueue';
import { ListenQueuePlayer } from '../components/ListenQueuePlayer';
import * as api from '../api';
import type { WorkflowArticle } from '../lib/workflowTypes';

function makeArticle(overrides: Partial<WorkflowArticle> = {}): WorkflowArticle {
  return {
    id: '1',
    title: 'An article',
    sourceId: 'source',
    sourceName: 'Source',
    category: 'ai-llm',
    url: 'https://example.com/a',
    publishedAt: '2026-06-16T10:00:00Z',
    ingestedAt: '2026-06-16T11:00:00Z',
    reason: 'why',
    summary: 'summary',
    signal: 'high',
    tags: [],
    bodyStatus: 'missing',
    state: 'today',
    starred: false,
    ...overrides,
  };
}

function Starter({ articles }: { articles: WorkflowArticle[] }) {
  const { start } = useListenQueue();
  return (
    <button type="button" onClick={() => start(articles)}>
      start
    </button>
  );
}

beforeEach(() => {
  vi.spyOn(api, 'fetchArticleAudioUrl').mockResolvedValue('blob:fake');
  vi.stubGlobal(
    'Audio',
    vi.fn().mockImplementation(function AudioMock() {
      return {
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        play: vi.fn().mockResolvedValue(undefined),
        pause: vi.fn(),
        removeAttribute: vi.fn(),
      };
    })
  );
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function renderPlayer(articles: WorkflowArticle[]) {
  return render(
    <MemoryRouter>
      <ListenQueueProvider>
        <Starter articles={articles} />
        <ListenQueuePlayer />
      </ListenQueueProvider>
    </MemoryRouter>
  );
}

describe('ListenQueuePlayer', () => {
  it('renders nothing when no queue is active', () => {
    renderPlayer([makeArticle()]);
    expect(screen.queryByRole('region', { name: /listen queue player/i })).toBeNull();
  });

  it('shows the current article and position once a queue starts', async () => {
    renderPlayer([
      makeArticle({ id: '1', title: 'First' }),
      makeArticle({ id: '2', title: 'Second' }),
    ]);

    fireEvent.click(screen.getByText('start'));

    await waitFor(() => expect(screen.getByText('First')).toBeTruthy());
    expect(screen.getByText('1/2')).toBeTruthy();
  });

  it('closing the player clears the queue', async () => {
    renderPlayer([makeArticle({ id: '1', title: 'First' })]);
    fireEvent.click(screen.getByText('start'));
    await waitFor(() => expect(screen.getByText('First')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: /close player/i }));

    await waitFor(() =>
      expect(screen.queryByRole('region', { name: /listen queue player/i })).toBeNull()
    );
  });

  it('previous is disabled on the first item and next is disabled on the last', async () => {
    renderPlayer([makeArticle({ id: '1' })]);
    fireEvent.click(screen.getByText('start'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Previous' })).toBeTruthy());

    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });
});
