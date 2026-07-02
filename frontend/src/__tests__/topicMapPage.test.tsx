// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TopicMapPage } from '../pages/TopicMapPage';
import * as api from '../api';
import type { TopicMapResponse } from '../types';

vi.mock('../api', () => ({
  fetchTopicMap: vi.fn(),
}));

const mockedApi = vi.mocked(api, true);

const TOPIC_MAP: TopicMapResponse = {
  clusters: [
    {
      id: 0,
      headline: 'AI chips heat up',
      trend_summary: 'Several vendors announced accelerators.',
      x: 0.1,
      y: 0.1,
      article_ids: [1, 2, 3],
      articles: [
        {
          id: 1,
          title: 'Vendor A ships chip',
          url: 'https://example.com/1',
          summary: 'S1',
          category: 'tech',
          x: 0.0,
          y: 0.0,
        },
        {
          id: 2,
          title: 'Vendor B ships chip',
          url: 'https://example.com/2',
          summary: 'S2',
          category: 'tech',
          x: 0.2,
          y: 0.1,
        },
        {
          id: 3,
          title: 'Vendor C ships chip',
          url: 'https://example.com/3',
          summary: 'S3',
          category: 'business',
          x: 0.1,
          y: 0.2,
        },
      ],
    },
  ],
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={['/topic-map']}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/topic-map" element={<TopicMapPage />} />
          <Route path="/a/:id" element={<div>article detail</div>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  mockedApi.fetchTopicMap.mockResolvedValue(TOPIC_MAP);
});

describe('TopicMapPage embedding scatter', () => {
  it('renders one point per article at its own position (no orbit rings)', async () => {
    const { container } = renderPage();
    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="article-point"]')).toHaveLength(3);
    });
    const points = [...container.querySelectorAll('[data-testid="article-point"]')];
    const xs = new Set(points.map((p) => p.getAttribute('cx')));
    // Distinct per-article coordinates, not a shared orbit radius.
    expect(xs.size).toBeGreaterThan(1);
  });

  it('draws a convex hull path for the cluster', async () => {
    const { container } = renderPage();
    await waitFor(() => {
      expect(container.querySelector('[data-testid="cluster-hull"]')).not.toBeNull();
    });
  });

  it('shows the cluster headline label', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('AI chips heat up')).toBeInTheDocument();
    });
  });

  it('navigates to the article when a point is clicked', async () => {
    const { container } = renderPage();
    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="article-point"]')).toHaveLength(3);
    });
    fireEvent.click(container.querySelectorAll('[data-testid="article-point"]')[0]);
    await waitFor(() => {
      expect(screen.getByText('article detail')).toBeInTheDocument();
    });
  });
});
