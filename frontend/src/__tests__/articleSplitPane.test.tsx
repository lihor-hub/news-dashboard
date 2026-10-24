// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Inbox } from 'lucide-react';
import '../lib/i18n';
import { FocusedArticleProvider } from '../contexts/focusedArticle';
import { ListenQueueProvider } from '../contexts/listenQueue';
import { ArticleListView } from '../components/article/ArticleListView';
import type { ArticleReaderProps } from '../components/article/ArticleReader';
import type { WorkflowArticle } from '../lib/workflowTypes';
import type { TriageArticlePage } from '../api/workflowApi';

vi.mock('../hooks/useTriageMutations', () => ({
  useTriageMutations: () => ({ setState: vi.fn(), toggleStar: vi.fn(), sendLater: vi.fn() }),
  ARTICLES_KEY: 'articles',
}));

const readerProps = vi.fn();
vi.mock('../components/article/ArticleReader', () => ({
  ArticleReader: (props: ArticleReaderProps) => {
    readerProps(props);
    return (
      <div data-testid="pane-reader" data-article-id={props.articleId}>
        <button type="button" onClick={props.onBack}>
          close pane
        </button>
      </div>
    );
  },
}));

let desktop = true;
function installMatchMedia() {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('min-width: 1024px') ? desktop : false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  );
}

function makeArticle(id: string, title: string): WorkflowArticle {
  return {
    id,
    title,
    sourceId: 'source',
    sourceName: 'Source',
    category: 'ai-llm',
    url: `https://example.com/${id}`,
    publishedAt: '2026-06-16T10:00:00Z',
    ingestedAt: '2026-06-16T11:00:00Z',
    reason: 'Why it matters.',
    summary: 'Summary.',
    signal: 'high',
    tags: [],
    bodyStatus: 'missing',
    state: 'today',
    starred: false,
  };
}

const ARTICLES = [
  makeArticle('1', 'First story'),
  makeArticle('2', 'Second story'),
  makeArticle('3', 'Third story'),
];

function page(items: WorkflowArticle[]): TriageArticlePage {
  return { items, limit: 100, offset: 0, hasMore: false };
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
}

function renderList(
  initialEntry = '/today',
  queryFn: () => Promise<TriageArticlePage> = () => Promise.resolve(page(ARTICLES)),
  { autoSelectFirst = false }: { autoSelectFirst?: boolean } = {}
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <FocusedArticleProvider>
        <ListenQueueProvider>
          <MemoryRouter initialEntries={[initialEntry]}>
            <Routes>
              <Route
                path="/today"
                element={
                  <ArticleListView
                    title="Today"
                    description={({ count }) => `${count} unhandled`}
                    queryKey={['articles', 'today']}
                    queryFn={queryFn}
                    empty={{ icon: Inbox, title: 'Queue clear' }}
                    autoSelectFirst={autoSelectFirst}
                  />
                }
              />
              <Route path="/a/:id" element={<div data-testid="full-reader">Full reader</div>} />
            </Routes>
            <LocationProbe />
          </MemoryRouter>
        </ListenQueueProvider>
      </FocusedArticleProvider>
    </QueryClientProvider>
  );
  return { ...utils, queryClient };
}

const location = () => screen.getByTestId('location').textContent;
const rowLink = (name: string) => screen.getByRole('link', { name: new RegExp(name, 'i') });

describe('ArticleListView split pane (lg+)', () => {
  beforeEach(() => {
    desktop = true;
    installMatchMedia();
    readerProps.mockClear();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders a list pane and an empty reading pane until an article is selected', async () => {
    renderList();
    await screen.findByText('First story');

    expect(screen.getByTestId('split-pane')).toBeTruthy();
    expect(screen.getByText('Select an article')).toBeTruthy();
    expect(screen.queryByTestId('pane-reader')).toBeNull();
    // Rows link to the in-page selection so middle-click and back keep working.
    expect(rowLink('first story').getAttribute('href')).toBe('/today?a=1');
  });

  it('shows the clicked article in the reading pane and syncs it to the URL', async () => {
    renderList();
    await screen.findByText('First story');

    fireEvent.click(rowLink('second story'));

    await waitFor(() => expect(location()).toBe('/today?a=2'));
    expect(screen.getByTestId('pane-reader').getAttribute('data-article-id')).toBe('2');
    expect(rowLink('second story').getAttribute('aria-current')).toBe('true');
    const props = readerProps.mock.calls.at(-1)![0] as ArticleReaderProps;
    expect(props.variant).toBe('pane');
    expect(props.enableShortcuts).toBe(false);
    expect(props.prevId).toBe('1');
    expect(props.nextId).toBe('3');
  });

  it('selects the article from a deep link', async () => {
    renderList('/today?a=3');
    await screen.findByText('First story');

    expect(screen.getByTestId('pane-reader').getAttribute('data-article-id')).toBe('3');
    expect(rowLink('third story').getAttribute('aria-current')).toBe('true');
  });

  it('moves the selection with J/K and opens the full page with Enter', async () => {
    renderList();
    await screen.findByText('First story');

    fireEvent.keyDown(window, { key: 'j' });
    await waitFor(() => expect(location()).toBe('/today?a=1'));
    fireEvent.keyDown(window, { key: 'j' });
    await waitFor(() => expect(location()).toBe('/today?a=2'));
    await waitFor(() =>
      expect(screen.getByTestId('pane-reader').getAttribute('data-article-id')).toBe('2')
    );
    fireEvent.keyDown(window, { key: 'k' });
    await waitFor(() => expect(location()).toBe('/today?a=1'));

    fireEvent.keyDown(window, { key: 'Enter' });
    await screen.findByTestId('full-reader');
    expect(location()).toBe('/a/1');
  });

  it('steps once per key press even when presses outrun the re-render', async () => {
    renderList();
    await screen.findByText('First story');

    fireEvent.keyDown(window, { key: 'j' });
    fireEvent.keyDown(window, { key: 'j' });
    fireEvent.keyDown(window, { key: 'j' });

    await waitFor(() => expect(location()).toBe('/today?a=3'));
  });

  it('leaves Enter to focused controls instead of opening the full page', async () => {
    renderList('/today?a=2');
    await screen.findByTestId('pane-reader');

    const close = screen.getByRole('button', { name: 'close pane' });
    fireEvent.keyDown(close, { key: 'Enter' });

    expect(screen.queryByTestId('full-reader')).toBeNull();
    expect(location()).toBe('/today?a=2');
  });

  it('hands the keyboard to the reader when the article is not in the loaded list', async () => {
    renderList('/today?a=99');
    await screen.findByText('First story');

    const props = readerProps.mock.calls.at(-1)![0] as ArticleReaderProps;
    expect(props.articleId).toBe('99');
    expect(props.enableShortcuts).toBe(true);
  });

  it('clears the selection with Escape and with the pane close action', async () => {
    renderList('/today?a=2');
    await screen.findByTestId('pane-reader');

    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => expect(location()).toBe('/today'));
    expect(screen.getByText('Select an article')).toBeTruthy();

    fireEvent.click(rowLink('first story'));
    await screen.findByTestId('pane-reader');
    fireEvent.click(screen.getByRole('button', { name: 'close pane' }));
    await waitFor(() => expect(location()).toBe('/today'));
  });

  it('advances to the next article when the selected one leaves the list', async () => {
    let items = ARTICLES;
    const { queryClient } = renderList('/today?a=2', () => Promise.resolve(page(items)));
    await screen.findByText('Second story');

    items = ARTICLES.filter((a) => a.id !== '2');
    await act(() => queryClient.invalidateQueries({ queryKey: ['articles'] }));

    await waitFor(() => expect(location()).toBe('/today?a=3'));
    await waitFor(() =>
      expect(screen.getByTestId('pane-reader').getAttribute('data-article-id')).toBe('3')
    );
  });

  it('auto-selects the first article only when asked to', async () => {
    renderList('/today', undefined, { autoSelectFirst: true });
    await waitFor(() => expect(location()).toBe('/today?a=1'));
  });

  it('keeps the regular empty state when the list is empty', async () => {
    renderList('/today', () => Promise.resolve(page([])));
    await screen.findByText('Queue clear');
    expect(screen.queryByTestId('split-pane')).toBeNull();
  });
});

describe('ArticleListView below lg', () => {
  beforeEach(() => {
    desktop = false;
    installMatchMedia();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('keeps rows linking to the full article page without a reading pane', async () => {
    renderList('/today?a=2');
    await screen.findByText('First story');

    expect(screen.queryByTestId('split-pane')).toBeNull();
    expect(screen.queryByTestId('pane-reader')).toBeNull();
    const list = screen.getByText('First story').closest('a')!;
    expect(list.getAttribute('href')).toBe('/a/1');
    expect(within(document.body).queryByText('Select an article')).toBeNull();
  });
});
