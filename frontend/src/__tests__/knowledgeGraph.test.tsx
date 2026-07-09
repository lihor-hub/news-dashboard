// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AiStatsPage } from '../pages/AiStatsPage';
import * as api from '../api';
import type { EmbeddingMapResponse, KnowledgeGraphResponse, WordCloudResponse } from '../types';

vi.mock('../api', () => ({
  fetchAiWordCloud: vi.fn(),
  fetchAiEmbeddingMap: vi.fn(),
  fetchKnowledgeGraph: vi.fn(),
}));

const mockedApi = vi.mocked(api, true);

const WORD_CLOUD: WordCloudResponse = { terms: [], article_count: 0, days: 7 };
const EMBEDDING_MAP: EmbeddingMapResponse = {
  points: [],
  clusters: [],
  embedded_count: 0,
  total_count: 0,
  days: 7,
};

const GRAPH: KnowledgeGraphResponse = {
  nodes: [
    { id: 'org:openai', name: 'OpenAI', type: 'org', count: 3, article_ids: [1, 2, 3] },
    { id: 'person:sam-altman', name: 'Sam Altman', type: 'person', count: 2, article_ids: [1, 2] },
    { id: 'place:paris', name: 'Paris', type: 'place', count: 1, article_ids: [3] },
  ],
  edges: [
    {
      source: 'org:openai',
      target: 'person:sam-altman',
      weight: 2,
      article_ids: [1, 2],
      kind: 'cooccurrence',
      label: 'co-mentioned',
    },
    {
      source: 'org:openai',
      target: 'person:sam-altman',
      weight: 1,
      article_ids: [1],
      kind: 'typed',
      relationship_type: 'led_by',
      label: 'led by',
    },
  ],
  articles: [
    { id: 1, title: 'OpenAI and Altman' },
    { id: 2, title: 'Altman speaks' },
    { id: 3, title: 'OpenAI in Paris' },
  ],
  article_count: 10,
  pending_count: 0,
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
  mockedApi.fetchKnowledgeGraph.mockResolvedValue(GRAPH);
});

describe('knowledge graph section', () => {
  it('renders a node per entity and an edge per co-occurrence', async () => {
    const { container } = renderPage();
    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="kg-node"]')).toHaveLength(3);
    });
    expect(container.querySelectorAll('[data-testid="kg-edge"]')).toHaveLength(2);
    expect(screen.getByText('OpenAI')).toBeInTheDocument();
    expect(screen.getByText('Sam Altman')).toBeInTheDocument();
  });

  it('reveals the entity’s articles when a node is clicked', async () => {
    const { container } = renderPage();
    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="kg-node"]')).toHaveLength(3);
    });
    const openai = [...container.querySelectorAll('[data-testid="kg-node"]')].find(
      (n) => n.getAttribute('data-entity') === 'org:openai'
    )!;
    fireEvent.click(openai);
    await waitFor(() => {
      expect(screen.getAllByText('OpenAI and Altman').length).toBeGreaterThan(0);
    });
    expect(screen.getByText('OpenAI in Paris')).toBeInTheDocument();
  });

  it('shows relationship summaries for the selected entity', async () => {
    const { container } = renderPage();
    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="kg-node"]')).toHaveLength(3);
    });
    const openai = [...container.querySelectorAll('[data-testid="kg-node"]')].find(
      (n) => n.getAttribute('data-entity') === 'org:openai'
    )!;
    fireEvent.click(openai);

    await waitFor(() => {
      expect(screen.getByText('Relationships')).toBeInTheDocument();
    });
    expect(screen.getByText(/led by Sam Altman/i)).toBeInTheDocument();
    expect(screen.getAllByText(/OpenAI and Altman/i).length).toBeGreaterThan(0);
  });

  it('filters the graph to typed relationships', async () => {
    const { container } = renderPage();
    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="kg-edge"]')).toHaveLength(2);
    });

    fireEvent.click(screen.getByRole('button', { name: /typed relationships/i }));

    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="kg-edge"]')).toHaveLength(1);
    });
    expect(container.querySelector('[data-testid="kg-edge"]')?.getAttribute('data-kind')).toBe(
      'typed'
    );
  });

  it('explains pending extraction in the empty state', async () => {
    mockedApi.fetchKnowledgeGraph.mockResolvedValue({
      ...GRAPH,
      nodes: [],
      edges: [],
      articles: [],
      pending_count: 12,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/still running for 12 articles/i)).toBeInTheDocument();
    });
  });
});
