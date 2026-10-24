// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Inbox, Plus } from 'lucide-react';
import * as api from '../api';
import '../lib/i18n';
import { EmptyState } from '../components/EmptyState';
import { ListSkeleton } from '../components/PageState';
import { TodayEmptyState } from '../components/TodayEmptyState';
import type { Source } from '../types';

function source(overrides: Partial<Source> = {}): Source {
  return {
    slug: 'hn',
    name: 'HN',
    url: 'https://news.ycombinator.com',
    category: 'tech',
    kind: 'rss',
    priority: 0,
    enabled: 1,
    owner_user_id: null,
    subscribed: true,
    ...overrides,
  } as Source;
}

function renderWithProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('EmptyState', () => {
  it('renders title, explanation and primary + secondary actions', () => {
    const onClick = vi.fn();
    renderWithProviders(
      <EmptyState
        icon={Inbox}
        title="Nothing here"
        subtitle="Explain why."
        actions={[
          { label: 'Add feeds', to: '/feeds', icon: Plus },
          { label: 'Dismiss', onClick },
        ]}
      />
    );
    expect(screen.getByRole('heading', { name: 'Nothing here' })).toBeTruthy();
    expect(screen.getByText('Explain why.')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Add feeds' }).getAttribute('href')).toBe('/feeds');
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(onClick).toHaveBeenCalled();
  });

  it('keeps action tap targets at least 44px tall on mobile', () => {
    renderWithProviders(
      <EmptyState icon={Inbox} title="Empty" actions={[{ label: 'Go', to: '/today' }]} />
    );
    expect(screen.getByRole('link', { name: 'Go' }).className).toContain('h-11');
  });
});

describe('ListSkeleton', () => {
  it('renders row-shaped placeholders announced as loading', () => {
    renderWithProviders(<ListSkeleton rows={3} />);
    const status = screen.getByRole('status');
    expect(status.getAttribute('aria-busy')).toBe('true');
    expect(screen.getByText('Loading')).toBeTruthy();
    expect(status.querySelectorAll('.rounded-lg')).toHaveLength(3);
  });
});

describe('TodayEmptyState', () => {
  it('shows the caught-up state with links to Learn, Weekly recap and Later', async () => {
    vi.spyOn(api, 'fetchSources').mockResolvedValue([source()]);
    renderWithProviders(<TodayEmptyState />);
    expect(await screen.findByRole('heading', { name: "You're all caught up" })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Learn something' }).getAttribute('href')).toBe(
      '/learn'
    );
    expect(screen.getByRole('link', { name: 'Weekly recap' }).getAttribute('href')).toBe('/recap');
    expect(screen.getByRole('link', { name: 'Open Later' }).getAttribute('href')).toBe('/later');
  });

  it('asks the reader to add feeds when they follow none', async () => {
    vi.spyOn(api, 'fetchSources').mockResolvedValue([source({ subscribed: false, enabled: 0 })]);
    renderWithProviders(<TodayEmptyState />);
    expect(
      await screen.findByRole('heading', { name: 'Add 3 feeds to get your first Brief' })
    ).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Add feeds' }).getAttribute('href')).toBe('/feeds');
  });

  it('offers to clear the category filter when a category is selected', async () => {
    vi.spyOn(api, 'fetchSources').mockResolvedValue([source()]);
    renderWithProviders(<TodayEmptyState category="ai-llm" />);
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Nothing new in this category' })).toBeTruthy()
    );
    expect(screen.getByRole('link', { name: 'Show all categories' }).getAttribute('href')).toBe(
      '/today'
    );
  });
});
