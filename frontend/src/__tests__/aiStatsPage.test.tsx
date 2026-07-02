// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AiStatsPage } from '../pages/AiStatsPage';
import * as api from '../api';
import type { EmbeddingMapResponse, WordCloudResponse } from '../types';

vi.mock('../api', () => ({
  fetchAiWordCloud: vi.fn(),
  fetchAiEmbeddingMap: vi.fn(),
}));

const mockedApi = vi.mocked(api, true);

const WORD_CLOUD: WordCloudResponse = {
  terms: [
    { term: 'kubernetes', count: 12, weight: 1 },
    { term: 'quantum', count: 5, weight: 0.6 },
  ],
  article_count: 40,
  days: 7,
};

const EMBEDDING_MAP: EmbeddingMapResponse = {
  points: [
    { id: 1, title: 'Alpha article', category: 'tech', x: 0.5, y: -0.5, cluster: 0 },
    { id: 2, title: 'Beta article', category: 'science', x: -0.4, y: 0.2, cluster: 1 },
  ],
  clusters: [
    { id: 0, label: 'alpha · topic', size: 1 },
    { id: 1, label: 'beta · subject', size: 1 },
  ],
  embedded_count: 2,
  total_count: 10,
  days: 7,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <AiStatsPage />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  mockedApi.fetchAiWordCloud.mockResolvedValue(WORD_CLOUD);
  mockedApi.fetchAiEmbeddingMap.mockResolvedValue(EMBEDDING_MAP);
});

describe('AiStatsPage', () => {
  it('renders word cloud terms as SVG text', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('kubernetes')).toBeInTheDocument();
    });
    expect(screen.getByText('quantum')).toBeInTheDocument();
  });

  it('renders one embedding-map point per article', async () => {
    const { container } = renderPage();
    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="embedding-point"]')).toHaveLength(2);
    });
  });

  it('shows the embedding coverage note', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/2 of 10 articles/i)).toBeInTheDocument();
    });
  });

  it('shows an error state with retry when the word cloud fails', async () => {
    mockedApi.fetchAiWordCloud.mockRejectedValue(new Error('boom'));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/failed to load word cloud/i)).toBeInTheDocument();
    });
    expect(screen.getAllByRole('button', { name: /retry/i }).length).toBeGreaterThan(0);
  });

  it('refetches with the selected range when a days option is clicked', async () => {
    renderPage();
    await waitFor(() => {
      expect(mockedApi.fetchAiWordCloud).toHaveBeenCalledWith(7);
    });
    screen.getByRole('button', { name: '30d' }).click();
    await waitFor(() => {
      expect(mockedApi.fetchAiWordCloud).toHaveBeenCalledWith(30);
    });
  });
});
