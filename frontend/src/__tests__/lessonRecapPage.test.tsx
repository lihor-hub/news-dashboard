// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import * as api from '../api';
import { LessonRecapPage } from '../pages/LessonRecapPage';
import type { LessonRecap } from '../types';

vi.mock('../api', () => ({
  fetchLessonRecaps: vi.fn(),
  generateLessonRecap: vi.fn(),
  generateLessonRecapPodcast: vi.fn(),
}));

function Wrapper({ children }: { children: React.ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

const RECAP: LessonRecap = {
  id: 1,
  user_id: 1,
  week_start: '2026-06-29',
  created_at: '2026-07-06T00:00:00+00:00',
  narrative: 'You completed 2 lessons this week, mostly about gradient descent.',
  podcast_status: null,
  podcast_error: null,
  data: {
    week_start: '2026-06-29',
    week_end: '2026-07-06',
    generated_at: '2026-07-06T00:00:00+00:00',
    lessons_touched: 3,
    lessons_completed: 2,
    key_concepts: [{ concept: 'gradient descent', count: 2 }],
    repeated_themes: [{ concept: 'gradient descent', count: 2 }],
    unfinished_lessons: [
      {
        id: 9,
        title: 'Still Pending',
        original_url: 'https://example.com/pending',
        generation_status: 'pending',
      },
    ],
    notable_articles: [
      { id: 5, title: 'Backprop Explained', source_name: 'Example Source', verdict: 'study' },
    ],
  },
};

const EMPTY_RECAP: LessonRecap = {
  ...RECAP,
  id: 2,
  narrative: null,
  data: {
    ...RECAP.data,
    lessons_touched: 0,
    lessons_completed: 0,
    key_concepts: [],
    repeated_themes: [],
    unfinished_lessons: [],
    notable_articles: [],
  },
};

beforeEach(() => {
  vi.resetAllMocks();
});

describe('LessonRecapPage', () => {
  it('renders key concepts, unfinished lessons, and notable articles', async () => {
    vi.mocked(api.fetchLessonRecaps).mockResolvedValue([RECAP]);
    render(<LessonRecapPage />, { wrapper: Wrapper });

    await screen.findByText('Key concepts');
    expect(screen.getAllByText('gradient descent').length).toBeGreaterThan(0);
    expect(screen.getByText('Still Pending')).toBeInTheDocument();
    expect(screen.getByText('Backprop Explained')).toBeInTheDocument();
    expect(
      screen.getByText('You completed 2 lessons this week, mostly about gradient descent.')
    ).toBeInTheDocument();
  });

  it('renders an empty state when there is no recap yet', async () => {
    vi.mocked(api.fetchLessonRecaps).mockResolvedValue([]);
    render(<LessonRecapPage />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(
        screen.getByText(
          'No recap yet — finish a lesson this week, then check back or generate one now.'
        )
      ).toBeInTheDocument();
    });
  });

  it('does not render a podcast player when podcast audio has not been generated', async () => {
    vi.mocked(api.fetchLessonRecaps).mockResolvedValue([EMPTY_RECAP]);
    render(<LessonRecapPage />, { wrapper: Wrapper });

    await screen.findByText('Podcast audio');
    expect(screen.getByText('Create podcast')).toBeInTheDocument();
    expect(screen.queryByRole('audio')).not.toBeInTheDocument();
    expect(screen.queryByText('Unfinished lessons')).not.toBeInTheDocument();
    expect(screen.queryByText('Notable articles')).not.toBeInTheDocument();
  });
});
